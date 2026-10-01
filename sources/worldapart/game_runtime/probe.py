"""Read-only WorldApart runtime inspection. Never requests write/operation access."""
import argparse, ctypes as C, ctypes.wintypes as W, json, struct, time, pathlib, collections, re, ntpath
from game_install import EXECUTABLE_NAME, same_executable, validate_installation
from write_guard import Refused

K = C.WinDLL('kernel32', use_last_error=True)
P = C.WinDLL('psapi', use_last_error=True)
class MBI(C.Structure):
    _fields_ = [('BaseAddress', C.c_void_p), ('AllocationBase', C.c_void_p),
                ('AllocationProtect', W.DWORD), ('PartitionId', W.WORD),
                ('RegionSize', C.c_size_t), ('State', W.DWORD),
                ('Protect', W.DWORD), ('Type', W.DWORD)]
K.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD]; K.OpenProcess.restype=W.HANDLE
K.CloseHandle.argtypes=[W.HANDLE]; K.CloseHandle.restype=W.BOOL
K.VirtualQueryEx.argtypes=[W.HANDLE,C.c_void_p,C.POINTER(MBI),C.c_size_t]; K.VirtualQueryEx.restype=C.c_size_t
K.ReadProcessMemory.argtypes=[W.HANDLE,C.c_void_p,C.c_void_p,C.c_size_t,C.POINTER(C.c_size_t)]; K.ReadProcessMemory.restype=W.BOOL
K.QueryFullProcessImageNameW.argtypes=[W.HANDLE,W.DWORD,W.LPWSTR,C.POINTER(W.DWORD)]; K.QueryFullProcessImageNameW.restype=W.BOOL
K.QueryDosDeviceW.argtypes=[W.LPCWSTR,W.LPWSTR,W.DWORD]; K.QueryDosDeviceW.restype=W.DWORD
P.GetMappedFileNameW.argtypes=[W.HANDLE,C.c_void_p,W.LPWSTR,W.DWORD]; P.GetMappedFileNameW.restype=W.DWORD
class WSX(C.Structure):
    _fields_=[('VirtualAddress',C.c_void_p),('Flags',C.c_size_t)]
P.QueryWorkingSetEx.argtypes=[W.HANDLE,C.c_void_p,W.DWORD];P.QueryWorkingSetEx.restype=W.BOOL

def hx(x): return hex(x) if x is not None else None

def process_path(pid):
    """Query identity with limited access before requesting any memory reads."""
    if type(pid) is not int or not 0 < pid <= 0xFFFFFFFF:
        raise Refused('游戏进程编号无效。')
    handle=K.OpenProcess(0x1000,False,pid)
    if not handle:raise OSError(C.get_last_error(),'无法查询游戏进程路径。')
    try:
        b=C.create_unicode_buffer(32768);n=W.DWORD(len(b))
        if not K.QueryFullProcessImageNameW(handle,0,b,C.byref(n)):
            raise OSError(C.get_last_error(),'无法读取游戏进程路径。')
        return b.value
    finally:K.CloseHandle(handle)

def mapped_path_matches(mapped, expected):
    """Match PSAPI's device path to the selected file without suffix guessing."""
    if not mapped:return False
    expected=ntpath.normpath(str(expected))
    actual=ntpath.normpath(mapped)
    if actual.startswith('\\\\?\\'):actual=actual[4:]
    if expected.startswith('\\\\?\\'):expected=expected[4:]
    if actual.casefold()==expected.casefold():return True
    if actual.casefold().startswith('\\device\\mup\\'):
        return ('\\\\'+actual[len('\\Device\\Mup\\'):]).casefold()==expected.casefold()
    drive,_=ntpath.splitdrive(expected)
    if len(drive)!=2 or drive[1]!=':':return False
    b=C.create_unicode_buffer(32768)
    if not K.QueryDosDeviceW(drive,b,len(b)):return False
    return (b.value+expected[len(drive):]).casefold()==actual.casefold()

class Reader:
    def __init__(self,pid,*,expected_path=None):
        if type(pid) is not int or not 0 < pid <= 0xFFFFFFFF:
            raise Refused('游戏进程编号无效。')
        self.h=K.OpenProcess(0x0010|0x0400,False,pid)
        if not self.h: raise OSError(C.get_last_error(),'OpenProcess read/query failed')
        try:
            b=C.create_unicode_buffer(32768); n=W.DWORD(len(b))
            if not K.QueryFullProcessImageNameW(self.h,0,b,C.byref(n)):
                raise Refused('无法读取游戏进程真实路径。')
            if pathlib.Path(b.value).name.casefold()!=EXECUTABLE_NAME.casefold():
                raise Refused('目标进程不是 WorldApart.exe。')
            if expected_path is not None and not same_executable(b.value,expected_path):
                raise Refused('运行中的游戏与所选 WorldApart.exe 路径不同，未连接。')
            self.installation=validate_installation(b.value)
            self.path=str(self.installation.executable_path)
            self.install_directory=self.installation.install_directory
            self.pid=pid;self.regions=list(self.iter_regions())
        except Exception:
            K.CloseHandle(self.h);self.h=None
            raise
    def close(self):
        if self.h:K.CloseHandle(self.h);self.h=None
    def read(self,addr,size):
        if not addr or size<=0 or size>4*1024*1024: return b''
        b=C.create_string_buffer(size); n=C.c_size_t()
        ok=K.ReadProcessMemory(self.h,C.c_void_p(addr),b,size,C.byref(n))
        return b.raw[:n.value] if ok or n.value else b''
    def u64(self,addr):
        b=self.read(addr,8); return struct.unpack('<Q',b)[0] if len(b)==8 else 0
    def string(self,addr,limit=256):
        return self.read(addr,limit).split(b'\0',1)[0].decode('utf-8',errors='replace')
    def query_region(self,addr):
        """Fresh page state, including freed/reserved spans omitted by iter_regions."""
        m=MBI()
        if K.VirtualQueryEx(self.h,C.c_void_p(addr),C.byref(m),C.sizeof(m)) != C.sizeof(m):
            return None
        return dict(base=m.BaseAddress or 0,size=m.RegionSize,state=m.State,
                    allocation=m.AllocationBase or 0,protect=m.Protect,type=m.Type)
    def iter_regions(self):
        a=0
        while a<0x7fffffffffff:
            m=MBI()
            if not K.VirtualQueryEx(self.h,C.c_void_p(a),C.byref(m),C.sizeof(m)): break
            base=m.BaseAddress or 0; size=m.RegionSize
            if m.State==0x1000 and not m.Protect&0x100 and m.Protect&0xff in (2,4,8,0x20,0x40,0x80):
                yield dict(base=base,size=size,allocation=m.AllocationBase or 0,protect=m.Protect,type=m.Type)
            if base+size<=a: break
            a=base+size
    def mapped(self,a):
        b=C.create_unicode_buffer(32768)
        return b.value if P.GetMappedFileNameW(self.h,C.c_void_p(a),b,len(b)) else ''
    def chunks(self,regions=None,chunk=2*1024*1024,resident=False):
        for r in regions or self.regions:
            for a in range(r['base'],r['base']+r['size'],chunk):
                size=min(chunk,r['base']+r['size']-a)
                spans=[(a,size)]
                if resident:
                    pages=(size+4095)//4096; ws=(WSX*pages)()
                    for i in range(pages):ws[i].VirtualAddress=a+i*4096
                    if not P.QueryWorkingSetEx(self.h,ws,C.sizeof(ws)):continue
                    spans=[];begin=None
                    for i in range(pages+1):
                        good=i<pages and bool(ws[i].Flags&1)
                        if good and begin is None:begin=i
                        if not good and begin is not None:
                            spans.append((a+begin*4096,min(size,i*4096)-begin*4096));begin=None
                for sa,sz in spans:
                    b=self.read(sa,sz)
                    if b: yield sa,b
                time.sleep(.004)
    def find(self,patterns,private=False,maxhits=1000):
        patterns={k:v for k,v in patterns.items() if v}
        bypat={v:k for k,v in patterns.items()}
        rx=re.compile(b'|'.join(re.escape(v) for v in bypat))
        out=collections.defaultdict(list); scanned=0; start=time.monotonic()
        regs=[r for r in self.regions if not private or r['type']==0x20000]
        for a,b in self.chunks(regs):
            scanned+=len(b)
            for m in rx.finditer(b):
                key=bypat[m.group()]
                if len(out[key])<maxhits: out[key].append(a+m.start())
        return dict(out),dict(bytes=scanned,seconds=round(time.monotonic()-start,2))

def do_map(r):
    counter=collections.Counter(); metadata=[];game_assembly=[]
    for reg in r.regions:
        counter[(reg['type'],reg['protect'])]+=reg['size']
        if reg['base']==reg['allocation']:
            mapped=r.mapped(reg['base']) if reg['type']==0x1000000 else ''
            if reg['type']==0x1000000 and mapped_path_matches(mapped,r.install_directory/'GameAssembly.dll'):
                game_assembly.append({**reg,'mapped_file':mapped})
            header=r.read(reg['base'],8)
            if header==struct.pack('<II',0xfab11baf,31):
                if not mapped:mapped=r.mapped(reg['base'])
                metadata.append({**reg,'mapped_file':mapped,
                    'installation_matches':mapped_path_matches(mapped,r.install_directory/'WorldApart_Data/il2cpp_data/Metadata/global-metadata.dat')})
    return dict(pid=r.pid,image=r.path,regions=len(r.regions),bytes=sum(x['size'] for x in r.regions),
                groups=[dict(type=hex(k[0]),protect=hex(k[1]),bytes=v) for k,v in counter.items()],
                metadata=metadata,game_assembly=game_assembly)

def verified_mappings(r):
    result=do_map(r)
    if (len(result['metadata'])!=1 or not result['metadata'][0]['installation_matches']
            or len(result['game_assembly'])!=1):
        raise Refused('尚未找到来自所选游戏目录的唯一 GameAssembly 与元数据映射；请等游戏进入存档后重试。')
    return result

TARGETS=['TalentPathModel','PlayerModel','BagModel','BagItemBase','BagItem']
def do_classes(r,max_mib):
    meta=verified_mappings(r)['metadata']
    if len(meta)!=1: raise RuntimeError('Expected exactly one metadata mapping')
    base=meta[0]['base']
    path=r.install_directory/'WorldApart_Data/il2cpp_data/Metadata/global-metadata.dat'
    data=path.read_bytes(); so,ss=struct.unpack_from('<II',data,24)
    desc=json.loads((pathlib.Path(__file__).parent.parent/'engine_game_types.json').read_text(encoding='utf-8-sig'))
    desc={x['name']:x for x in desc if x['name'] in TARGETS and x['image']=='Game.dll'}
    patterns={}; strings={}
    for name in TARGETS:
        needle=name.encode()+b'\0'; start=so
        while True:
            off=data.find(needle,start,so+ss)
            if off<0: break
            if off==so or data[off-1]==0:
                key=name+'@'+hex(off);patterns[key]=struct.pack('<Q',base+off);strings[key]=base+off
            start=off+1
    regs=sorted([x for x in r.regions if x['type']==0x20000 and x['protect']==4],key=lambda x:x['size'])
    budget=max_mib*1024*1024;scanned=0;hits=[];raw_hits=[];start=time.monotonic()
    bypat={v:k for k,v in patterns.items()};rx=re.compile(b'|'.join(re.escape(v) for v in bypat))
    for a,b in r.chunks(regs,resident=True):
        if scanned+len(b)>budget:break
        scanned+=len(b)
        for m in rx.finditer(b):
            candidate=a+m.start()-16
            if len(raw_hits)<50:raw_hits.append(dict(name=bypat[m.group()],candidate=hex(candidate),selfptr=hex(r.u64(candidate+0x78))))
            if candidate%8 or r.u64(candidate+0x78)!=candidate:continue
            name=bypat[m.group()].split('@')[0];record=desc[name]
            ns=r.string(r.u64(candidate+0x18))
            if ns!=record['namespace']:continue
            header=r.read(candidate,320)
            if len(header)!=320:continue
            field_count=struct.unpack_from('<H',header,0x124)[0]
            instance_size=struct.unpack_from('<I',header,0xf8)[0]
            fields_ptr=struct.unpack_from('<Q',header,0x80)[0]
            fields=[];valid=field_count==len(record['fields']) and 16<=instance_size<65536
            for i,expected in enumerate(record['fields']):
                f=r.read(fields_ptr+i*32,32)
                if len(f)!=32:valid=False;break
                np,tp,parent,offset,token=struct.unpack('<QQQiI',f)
                fname=r.string(np)
                if fname!=expected['name'] or parent!=candidate or token!=int(expected['token'],16):valid=False
                type_bytes=r.read(tp,16)
                fields.append(dict(name=fname,offset=offset,token=hex(token),type_pointer=hex(tp),type_data=type_bytes.hex()))
            hits.append(dict(name=name,namespace=ns,klass=hex(candidate),field_count=field_count,instance_size=instance_size,
                             fields_ptr=hex(fields_ptr),parent_class=hex(r.u64(candidate+0x58)),static_fields=hex(r.u64(candidate+0xb8)),
                             validated=valid,fields=fields))
    result=dict(pid=r.pid,metadata_base=hex(base),name_pointers={k:hex(v) for k,v in strings.items()},scanned_bytes=scanned,
                seconds=round(time.monotonic()-start,2),classes=hits,raw_hits=raw_hits)
    out=pathlib.Path(__file__).parent/'classes.json';out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

def inspect_class(r,klass,*,max_fields=512):
    if type(max_fields) is not int or not 1 <= max_fields <= 1024:
        raise ValueError('Invalid bounded IL2CPP field limit')
    b=r.read(klass,320)
    if len(b)!=320 or struct.unpack_from('<Q',b,0x78)[0]!=klass:return None
    n=struct.unpack_from('<H',b,0x124)[0]
    # The reviewed pill-exploration UI has 300 fields. Keep a finite bound,
    # large enough to inspect it when walking the shared panel registry.
    if n>max_fields:return None
    fields=[]; fp=struct.unpack_from('<Q',b,0x80)[0]
    for i in range(n):
        f=r.read(fp+i*32,32)
        if len(f)!=32:return None
        name,ty,parent,offset,token=struct.unpack('<QQQiI',f)
        tb=r.read(ty,16)
        fields.append(dict(name=r.string(name),offset=offset,token=hex(token),type_data=tb.hex(),parent=hex(parent)))
    return dict(klass=hex(klass),name=r.string(struct.unpack_from('<Q',b,16)[0]),namespace=r.string(struct.unpack_from('<Q',b,24)[0]),
                parent=hex(struct.unpack_from('<Q',b,0x58)[0]),static_fields=hex(struct.unpack_from('<Q',b,0xb8)[0]),
                instance_size=struct.unpack_from('<I',b,0xf8)[0],fields=fields)

def do_objects(r,max_mib):
    classes=json.loads((pathlib.Path(__file__).parent/'classes.json').read_text(encoding='utf8'))
    cd={x['name']:x for x in classes['classes'] if x['validated']}
    pk=int(cd['PlayerModel']['klass'],16);bk=int(cd['BagModel']['klass'],16);tk=int(cd['TalentPathModel']['klass'],16)
    patterns={'PlayerModel':struct.pack('<Q',pk)}
    md=(r.install_directory/'WorldApart_Data/il2cpp_data/Metadata/global-metadata.dat').read_bytes()
    so,ss=struct.unpack_from('<II',md,24); off=md.find(b'\0GameStoreManager\0',so,so+ss)+1
    if off>so:patterns['GameStoreManager']=struct.pack('<Q',int(classes['metadata_base'],16)+off)
    bypat={v:k for k,v in patterns.items()};rx=re.compile(b'|'.join(re.escape(v) for v in bypat))
    regs=[x for x in r.regions if x['type']==0x20000 and x['protect']==4]
    scanned=0;objects=[];managers=[];start=time.monotonic();raw_count=0
    for a,b in r.chunks(regs,resident=True):
        if scanned+len(b)>max_mib*1024*1024:break
        scanned+=len(b)
        for m in rx.finditer(b):
            hit=a+m.start()
            if hit%8:continue
            key=bypat[m.group()]
            if key=='GameStoreManager':
                k=hit-16;info=inspect_class(r,k)
                if not info or info['name']!='GameStoreManager':continue
                mc=struct.unpack('<H',r.read(k+0x120,2))[0];mp=r.u64(k+0x98);methods=[]
                for i in range(min(mc,300)):
                    mi=r.u64(mp+i*8);name=r.string(r.u64(mi+0x18))
                    if name.startswith('get_Current') or name in ['.cctor','.ctor']:
                        methods.append(dict(name=name,method_info=hex(mi),method_pointer=hex(r.u64(mi)),token=r.read(mi+0x48,4).hex()))
                info['methods']=methods;managers.append(info);continue
            raw_count+=1
            bag=r.u64(hit+64);talent=r.u64(hit+112)
            if r.u64(bag)!=bk or r.u64(talent)!=tk:continue
            items=r.u64(bag+24);ic=r.u64(items)
            obj=dict(player=hex(hit),bag=hex(bag),talent=hex(talent),player_owner=hex(r.u64(hit+16)),bag_owner=hex(r.u64(bag+16)),
                     talent_owner=hex(r.u64(talent+16)),spirit_address=hex(talent+48),spirit=struct.unpack('<i',r.read(talent+48,4))[0],
                     root_points=hex(r.u64(talent+40)),items=hex(items),items_class=inspect_class(r,ic))
            objects.append(obj)
    result=dict(pid=r.pid,scanned_bytes=scanned,seconds=round(time.monotonic()-start,2),raw_player_references=raw_count,players=objects,managers=managers)
    (pathlib.Path(__file__).parent/'objects.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--pid',type=int,required=True);ap.add_argument('--mode',choices=['map','classes','objects'],default='map');ap.add_argument('--max-mib',type=int,default=1024);args=ap.parse_args()
    r=Reader(args.pid)
    try: print(json.dumps(do_map(r) if args.mode=='map' else do_classes(r,args.max_mib) if args.mode=='classes' else do_objects(r,args.max_mib),ensure_ascii=False,indent=2))
    finally:r.close()
if __name__=='__main__':main()
