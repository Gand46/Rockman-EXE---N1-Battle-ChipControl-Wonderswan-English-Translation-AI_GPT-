#!/usr/bin/env python3
"""Reproducible, hash-guarded binary experiment: Japanese N1 -> QA09 + WSC Chip Control RC6.

QA09 remains the official baseline; no changes to MANT03 source or BPS.
Requires the exact patches from the QA09 repository and this optional component, plus a user-provided original ROM.
This is NOT a substitute for missing editable ChipControl RC6 assembly sources.
"""
from __future__ import annotations
import argparse, hashlib, json, struct, sys, zlib
from pathlib import Path

JP_SHA='4aeaf266e8705772c832652d374e6147c544e37b45f6fd5b1ad9e0aa0d2fd6ed'
QA09_BPS_SHA='4fbfce1dcf2d0da714b936874167219e05076ad8ac40db0e43bb214eb063b0f2'
QA09_SHA='d729823bbe6cf9132e6345ed734eb2dbe51885c13d5a17a44a9f7cfae086c326'
A9_IPS_SHA='9a1bf3430a4e213eb10d3a1f340532dc43f4a7554fad83821263c21bef9e9cb5'
A9_SHA='27c189a8303ff1ba75a624ea686380c3d9bff618da2a06d8e3e1b0d8ceda53f6'
RC6_IPS_SHA='c4f088078bf42b6a3e56f3b42704ffe92377c91b32a98b3a0017461c92d0540b'
RC6_A9_SHA='18aa0fe6af0e49d37f135768d748941800480c2c385ddbd5ad08290d483a78e0'
ROM_SIZE=0x400000

def sha(raw:bytes)->str:return hashlib.sha256(raw).hexdigest()
def require_equal(actual, expected,what):
 if actual != expected:raise ValueError(f'{what}: unexpected SHA256/identity {actual} != {expected}')

def variable_int(b:bytes, p:int):
 value=0;shift=1
 while True:
  if p>=len(b):raise ValueError('BPS truncated variable length integer')
  x=b[p];p+=1;value+=(x&127)*shift
  if x&128:return value,p
  shift<<=7;value+=shift

def encode_int(n:int)->bytes:
 if n<0:raise ValueError('negative integer')
 out=bytearray()
 while True:
  x=n&127;n>>=7
  if not n:out.append(x|128);return bytes(out)
  out.append(x);n-=1

def apply_bps(original:bytes,patch:bytes)->bytes:
 if patch[:4]!=b'BPS1' or len(patch)<19:raise ValueError('invalid BPS')
 src_crc,dst_crc,patch_crc=struct.unpack('<III',patch[-12:])
 if zlib.crc32(original)!=src_crc or zlib.crc32(patch[:-4])!=patch_crc:raise ValueError('BPS CRC mismatch')
 p=4;ns,p=variable_int(patch,p);nd,p=variable_int(patch,p);metadata,p=variable_int(patch,p)
 if ns!=len(original) or p+metadata>len(patch)-12:raise ValueError('BPS source size/metadata mismatch')
 p+=metadata;out=bytearray();sr=tr=0;end=len(patch)-12
 while len(out)<nd:
  op,p=variable_int(patch,p);mode=op&3;count=(op>>2)+1
  if len(out)+count>nd:raise ValueError('BPS output exceeded')
  if mode==0:out.extend(original[len(out):len(out)+count])
  elif mode==1:
   if p+count>end:raise ValueError('truncated BPS bytes')
   out.extend(patch[p:p+count]);p+=count
  else:
   off,p=variable_int(patch,p);delta=(-1 if off&1 else 1)*(off>>1)
   if mode==2:
    sr+=delta
    if sr<0 or sr+count>len(original):raise ValueError('BPS source copy invalid')
    out.extend(original[sr:sr+count]);sr+=count
   else:
    tr+=delta
    if tr<0 or tr>=len(out):raise ValueError('BPS target copy invalid')
    for _ in range(count):
     if tr>=len(out):raise ValueError('BPS invalid target-copy')
     out.append(out[tr]);tr+=1
 if p!=end or zlib.crc32(out)!=dst_crc:raise ValueError('BPS trailing data or target CRC invalid')
 return bytes(out)

def build_bps(original:bytes,target:bytes)->bytes:
 out=bytearray(b'BPS1')+encode_int(len(original))+encode_int(len(target))+encode_int(0)
 i=0
 while i<len(target):
  eq=i<len(original) and original[i]==target[i];j=i+1
  while j<len(target) and (j<len(original) and original[j]==target[j])==eq:j+=1
  out+=encode_int(((j-i-1)<<2)|(0 if eq else 1))
  if not eq:out+=target[i:j]
  i=j
 out+=struct.pack('<II',zlib.crc32(original),zlib.crc32(target))
 out+=struct.pack('<I',zlib.crc32(out));return bytes(out)

def parse_ips(patch:bytes)->list[tuple[int,bytes]]:
 if patch[:5]!=b'PATCH':raise ValueError('missing IPS header')
 i=5;rows=[]
 while True:
  if i+3>len(patch):raise ValueError('truncated IPS')
  if patch[i:i+3]==b'EOF':
   if len(patch)!=i+3:raise ValueError('IPS truncated extension unsupported')
   break
  if i+5>len(patch):raise ValueError('truncated IPS record')
  offset=int.from_bytes(patch[i:i+3],'big');length=int.from_bytes(patch[i+3:i+5],'big');i+=5
  if length==0:
   if i+3>len(patch):raise ValueError('truncated IPS RLE')
   size=int.from_bytes(patch[i:i+2],'big');blob=patch[i+2:i+3]*size;i+=3
  else:
   if i+length>len(patch):raise ValueError('truncated IPS data')
   blob=patch[i:i+length];i+=length
  if offset+len(blob)>ROM_SIZE:raise ValueError('IPS exceeds target ROM')
  rows.append((offset,blob))
 return rows

def apply_ips(data:bytes,rows:list[tuple[int,bytes]])->bytes:
 buf=bytearray(data)
 for o,b in rows:buf[o:o+len(b)]=b
 return bytes(buf)

def analyse(original:bytes,qa09_bps:bytes,a9_ips:bytes,rc6_ips:bytes):
 require_equal(sha(original),JP_SHA,'original Japanese ROM')
 for raw,expected,name in [(qa09_bps,QA09_BPS_SHA,'QA09 BPS'),(a9_ips,A9_IPS_SHA,'English graphics-a9 IPS'),(rc6_ips,RC6_IPS_SHA,'ChipControl RC6 IPS')]:require_equal(sha(raw),expected,name)
 qa09=apply_bps(original,qa09_bps);require_equal(sha(qa09),QA09_SHA,'reconstructed QA09')
 a9=apply_ips(original,parse_ips(a9_ips));require_equal(sha(a9),A9_SHA,'graphics-a9 historical ROM')
 entries=parse_ips(rc6_ips)
 old_result=apply_ips(a9,entries);require_equal(sha(old_result),RC6_A9_SHA,'RC6 historical ROM')
 functional=[];checks=[];unexpected=[];locations=set()
 for o,blob in entries:
  for i,x in enumerate(blob):
   k=o+i
   if k in locations:raise ValueError(f'overlapping IPS entries at {k:#x}')
   locations.add(k)
   if k>=ROM_SIZE-2:checks.append(k);continue
   if qa09[k]!=a9[k]:unexpected.append((k,qa09[k],a9[k]))
   if qa09[k]==x:raise ValueError(f'RC6 patch is unexpectedly already present in QA09 at {k:#x}')
   functional.append(k)
 if unexpected:raise ValueError(f'{len(unexpected)} foreign modifications in RC6 target offsets; first {unexpected[:10]}')
 if len(entries)!=167 or len(functional)!=1959 or sorted(checks)!=[ROM_SIZE-2,ROM_SIZE-1]:raise ValueError('RC6 write-domain count changed')
 result=bytearray(qa09)
 for o,blob in entries:
  for i,x in enumerate(blob):
   if o+i<ROM_SIZE-2:result[o+i]=x
 checksum=sum(result[:-2])&0xffff;result[-2:]=checksum.to_bytes(2,'little');result=bytes(result)
 if sum(result[:-2])&0xffff != int.from_bytes(result[-2:],'little'):raise ValueError('invalid WonderSwan checksum')
 actual_diffs={i for i,(a,b) in enumerate(zip(qa09,result)) if a!=b}
 if actual_diffs!=locations:raise ValueError('actual modifications do not match allowed write set')
 preserve=sum(a!=b for i,(a,b) in enumerate(zip(qa09,result)) if i not in locations)
 assert preserve==0
 report={'status':'PASS_STATIC_EXPERIMENTAL_NOT_FINAL','jp_sha256':sha(original),'qa09_sha256':sha(qa09),'a9_sha256':sha(a9),'rc6_a9_sha256':sha(old_result),'experimental_rom_sha256':sha(result),'checksum_before_from_original_ips':'0x1BE8','checksum_rebuilt':f'0x{checksum:04X}','rc6_ips_sha256':sha(rc6_ips),'records':len(entries),'functional_bytes_written':len(functional),'checksum_bytes':len(checks),'total_written_bytes':len(locations),'functional_conflicts_with_QA09':len(unexpected),'out_of_scope_modified_bytes':preserve,'a9_to_qa09_differing_bytes':sum(a!=b for a,b in zip(a9,qa09)),'restricted_to_rom_size':len(result)==len(qa09)==ROM_SIZE,'original_QA09_unchanged':True,'rom_is_test_only':True,'rc6_source_assembly_available':False}
 return result,report

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--jp',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
 opt_root=Path(__file__).resolve().parents[1]
 repo_root=opt_root.parents[1]
 p.add_argument('--qa09-bps',type=Path,default=repo_root/'maintenance/baseline-patches/Rockman_N1_English_QA09.bps')
 p.add_argument('--a9-ips',type=Path,default=opt_root/'vendor/Rockman_EXE_N1_Battle_English_v0.10.7-graphics-a9.ips')
 p.add_argument('--rc6-ips',type=Path,default=opt_root/'vendor/ChipControl_v0.5.8_RC6_for_English_v0.10.7-graphics-a9.ips')
 p.add_argument('--emit-private-rom',action='store_true',help='Write testing ROM (never distribute this file)')
 args=p.parse_args()
 result,record=analyse(args.jp.read_bytes(),args.qa09_bps.read_bytes(),args.a9_ips.read_bytes(),args.rc6_ips.read_bytes())
 original=args.jp.read_bytes();bps=build_bps(original,result)
 if apply_bps(original,bps)!=result:raise ValueError('cumulative BPS roundtrip mismatch')
 args.out.mkdir(parents=True,exist_ok=True)
 bpspath=args.out/'Rockman_N1_English_QA09_ChipControl_RC6_EXPERIMENTAL.bps';bpspath.write_bytes(bps)
 record['cumulative_bps_sha256']=sha(bps);record['cumulative_bps_bytes']=len(bps)
 if args.emit_private_rom:
  (args.out/'DO_NOT_DISTRIBUTE_QA09_ChipControl_RC6.wsc').write_bytes(result)
 (args.out/'build_checks.json').write_text(json.dumps(record,indent=2,ensure_ascii=False)+'\n')
 print(json.dumps(record,indent=2))
 return 0
if __name__=='__main__':sys.exit(main())
