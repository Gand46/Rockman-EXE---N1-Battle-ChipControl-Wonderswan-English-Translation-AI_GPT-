"""Build a diagnostic-only core copy logging reads of the description region."""
from pathlib import Path
import shutil,subprocess,argparse
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
out=a.out.resolve();core=out/'emulator'
if not core.exists():shutil.copytree(ROOT/'qa/emulator',core,ignore=shutil.ignore_patterns('*.o','*.so','.git'))
f=core/'mednafen/wswan/wswan-memory.c';s=f.read_text();needle='   return(wsCartROM[(bank_num << 16) | offset]);'
code='''   { uint32 phys = (bank_num << 16) | offset;
     static unsigned count=0;
     if(phys>=0x36a4e0 && phys<0x36e1c8 && count++<10000)
       fprintf(stderr,"QREAD %06x %02x BANKS=%02x/%02x/%02x PC=%04x:%04x AX=%04x BX=%04x CX=%04x DX=%04x SI=%04x DI=%04x DS=%04x ES=%04x\\n",phys,wsCartROM[phys],BankSelector[0],BankSelector[2],BankSelector[3],v30mz_get_reg(NEC_PS),v30mz_get_reg(NEC_PC),v30mz_get_reg(NEC_AW),v30mz_get_reg(NEC_BW),v30mz_get_reg(NEC_CW),v30mz_get_reg(NEC_DW),v30mz_get_reg(NEC_IX),v30mz_get_reg(NEC_IY),v30mz_get_reg(NEC_DS0),v30mz_get_reg(NEC_DS1));
     return wsCartROM[phys];
   }'''
if 'QREAD' not in s:
 assert needle in s;s=s.replace(needle,code).replace('#include "wswan.h"','#include <stdio.h>\n#include "wswan.h"');f.write_text(s)
with (out/'core_build.log').open('w') as log:subprocess.run(['make','-j4'],cwd=core,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
print(core/'mednafen_wswan_libretro.so')
