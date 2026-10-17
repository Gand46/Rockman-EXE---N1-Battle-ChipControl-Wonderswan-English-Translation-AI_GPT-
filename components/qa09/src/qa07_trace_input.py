import ctypes as C,sys,json,os
from pathlib import Path
import numpy as np
from PIL import Image
root=Path(os.environ.get('QA_ENGINE_DIR',str(Path(__file__).resolve().parents[1]/'qa')))
core=C.CDLL(str(root/'emulator/mednafen_wswan_libretro.so'))
ENV=C.CFUNCTYPE(C.c_bool,C.c_uint,C.c_void_p); VID=C.CFUNCTYPE(None,C.c_void_p,C.c_uint,C.c_uint,C.c_size_t)
AUD=C.CFUNCTYPE(None,C.c_int16,C.c_int16); BATCH=C.CFUNCTYPE(C.c_size_t,C.c_void_p,C.c_size_t); POLL=C.CFUNCTYPE(None); INPUT=C.CFUNCTYPE(C.c_int16,C.c_uint,C.c_uint,C.c_uint,C.c_uint)
class Var(C.Structure): _fields_=[('key',C.c_char_p),('value',C.c_char_p)]
class Info(C.Structure): _fields_=[('path',C.c_char_p),('data',C.c_void_p),('size',C.c_size_t),('meta',C.c_char_p)]
mask=0; pixel=0; last=None
@ENV
def env(cmd,p):
 global pixel
 if cmd==10: pixel=C.cast(p,C.POINTER(C.c_int))[0]; return True
 if cmd==15:
  v=C.cast(p,C.POINTER(Var)); k=v[0].key
  options={b'wswan_rotate_display':b'manual',b'wswan_frameskip':b'disabled',b'wswan_60hz_mode':b'disabled',b'wswan_gfx_colors':b'16bit'}
  if k in options: v[0].value=options[k]; return True
  return False
 if cmd==17: C.cast(p,C.POINTER(C.c_bool))[0]=False; return True
 if cmd in (9,31): C.cast(p,C.POINTER(C.c_char_p))[0]=str(root/'work').encode(); return True
 return cmd in (11,18)
@VID
def video(p,w,h,pitch):
 global last
 if not p:return
 raw=C.string_at(p,h*pitch)
 if pixel==1:
  a=np.frombuffer(raw,dtype=np.uint32).reshape(h,pitch//4)[:,:w]; rgb=np.stack([(a>>16)&255,(a>>8)&255,a&255],axis=-1)
 else:
  a=np.frombuffer(raw,dtype=np.uint16).reshape(h,pitch//2)[:,:w]
  rgb=np.stack([((a>>11)&31)*255//31,((a>>5)&63)*255//63,(a&31)*255//31],axis=-1) if pixel==2 else np.stack([((a>>10)&31)*255//31,((a>>5)&31)*255//31,(a&31)*255//31],axis=-1)
 last=Image.fromarray(rgb.astype('uint8'))
@AUD
def audio(a,b):pass
@BATCH
def batch(p,n):return n
@POLL
def poll():pass
@INPUT
def inp(port,dev,idx,key): return bool(mask&(1<<key)) if key<16 else 0
for name,cb in [('environment',env),('video_refresh',video),('audio_sample',audio),('audio_sample_batch',batch),('input_poll',poll),('input_state',inp)]:getattr(core,'retro_set_'+name)(cb)
core.retro_init(); rom=Path(os.environ.get('AUDIT_ROM_DIR',str(root/'work')))/f'{sys.argv[1]}.wsc'; data=rom.read_bytes(); buf=C.create_string_buffer(data)
core.retro_load_game.argtypes=[C.POINTER(Info)];core.retro_load_game.restype=C.c_bool
assert core.retro_load_game(C.byref(Info(str(rom).encode(),C.cast(buf,C.c_void_p),len(data),None)))
core.retro_serialize_size.restype=C.c_size_t; core.retro_serialize.argtypes=[C.c_void_p,C.c_size_t];core.retro_unserialize.argtypes=[C.c_void_p,C.c_size_t]
steps=json.loads(Path(sys.argv[2]).read_text()); target=Path(os.environ.get('QA_CAPTURE_DIR',str(root/'captures_qa03')));target.mkdir(exist_ok=True)
if len(sys.argv)>3 and sys.argv[3]!='-':
 state=Path(sys.argv[3]).read_bytes(); sb=C.create_string_buffer(state); assert core.retro_unserialize(sb,len(state))
core.retro_get_memory_size.argtypes=[C.c_uint]; core.retro_get_memory_size.restype=C.c_size_t
core.retro_get_memory_data.argtypes=[C.c_uint]; core.retro_get_memory_data.restype=C.c_void_p
save_size=core.retro_get_memory_size(0); save_ptr=core.retro_get_memory_data(0)
if len(sys.argv)>4 and sys.argv[4]!='-':
 assert len(sys.argv)<4 or sys.argv[3]=='-', 'Cold load cannot combine save and savestate'
 saved=Path(sys.argv[4]).read_bytes(); assert len(saved)==save_size and save_ptr
 C.memmove(save_ptr,saved,save_size)
keys={'a':8,'b':0,'start':3,'up':4,'down':5,'left':6,'right':7,'yup':13,'ydown':12,'yleft':10,'yright':11}
for step in steps:
 mask=sum(1<<keys[k] for k in step.get('keys',[]))
 for _ in range(step['frames']):
  core.retro_run()
  if step.get('keys'):print('KEYTRACE',step['keys'],C.string_at(core.retro_get_memory_data(2)+0xce48,12).hex())
 if 'name' in step:
  name=sys.argv[1]+'_'+step['name'];last.save(target/(name+'.png'))
  sb=C.create_string_buffer(core.retro_serialize_size()); assert core.retro_serialize(sb,len(sb));(target/(name+'.state')).write_bytes(sb.raw)
  (target/(name+'.ram')).write_bytes(C.string_at(core.retro_get_memory_data(2),core.retro_get_memory_size(2)))
  print(name,last.size)
if len(sys.argv)>5 and sys.argv[5]!='-':
 assert save_size and save_ptr
 out=Path(sys.argv[5]); out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(C.string_at(save_ptr,save_size))
 print('Saved cartridge memory:',save_size,'bytes')
core.retro_unload_game();core.retro_deinit()
