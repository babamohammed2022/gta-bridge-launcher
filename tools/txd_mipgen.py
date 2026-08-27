#!/usr/bin/env python3
"""txd_mipgen.py - RW legacy TXD tools for GTA SA mobile-era layout.
Modes:
  --export SRCDIR OUTDIR   decode all txd textures -> DDS files (for Magic.TXD mass build)
  --batch DIR BACKUPDIR    in-place mipgen (raw32 only; DXT re-encode not supported here)
"""
import os, struct, sys, shutil
import numpy as np
from PIL import Image

FMT_A8R8G8B8 = 21
FMT_DXT1 = 0x31545844
FMT_DXT3 = 0x33545844
FMT_DXT5 = 0x35545844
HDR = 92
NULLBYTE = b'\x00'

def lvl_size(fmt,w,h):
    if fmt==FMT_A8R8G8B8: return w*h*4
    if fmt==FMT_DXT1: return max(1,(w+3)//4)*max(1,(h+3)//4)*8
    return max(1,(w+3)//4)*max(1,(h+3)//4)*16

def parse_chunks(buf,start,end):
    out=[]; i=start
    while i+12<=end:
        typ,size,ver=struct.unpack_from('<III',buf,i)
        out.append([typ,i,size])
        if typ in (0x16,0x15): out.extend(parse_chunks(buf,i+12,i+12+size))
        i+=12+size
    return out


def _rgb565(c):
    r=(c>>11)&31; g=(c>>5)&63; b=c&31
    return np.stack([(r<<3)|(r>>2),(g<<2)|(g>>4),(b<<3)|(b>>2)],-1).astype(np.uint8)

def dec_dxt1(blk,w,h):
    blk=np.frombuffer(bytes(blk),dtype=np.uint8).reshape(-1)
    n=blk.size//8; blk=blk.reshape(n,8)
    c0=np.frombuffer(blk[:,0:2].tobytes(),dtype='<u2')
    c1=np.frombuffer(blk[:,2:4].tobytes(),dtype='<u2')
    sel=np.frombuffer(blk[:,4:8].tobytes(),dtype=np.uint8).reshape(n,4)
    bits=(sel[:,0].astype(np.uint64)|sel[:,1].astype(np.uint64)<<8|
          sel[:,2].astype(np.uint64)<<16|sel[:,3].astype(np.uint64)<<24)
    p0=_rgb565(c0); p1=_rgb565(c1)
    rgb=np.zeros((n,16,3),np.uint8); a=np.full((n,16),255,np.uint8)
    gt=c0>c1
    half=((p0.astype(np.int16)+p1)//2).astype(np.uint8)
    for i in range(16):
        s=((bits>>(2*i))&3)
        v=np.where(s[...,None]==0,p0,np.where(s[...,None]==1,p1,half))
        trans=(~gt)&(s==3)
        v=np.where(trans[...,None],0,v)
        rgb[:,i]=v; a[:,i]=np.where(trans,0,255)
    return rgb.reshape(h,w,3),a.reshape(h,w)

def dec_dxt35(blk,w,h,dxt5):
    n=len(blk)//16; blk=np.frombuffer(bytes(blk),dtype=np.uint8).reshape(n,16)
    if dxt5:
        a0=blk[:,0].astype(np.int16); a1=blk[:,1].astype(np.int16)
        bits=(blk[:,2].astype(np.uint64)|blk[:,3].astype(np.uint64)<<8|blk[:,4].astype(np.uint64)<<16|
              blk[:,5].astype(np.uint64)<<24|blk[:,6].astype(np.uint64)<<32|blk[:,7].astype(np.uint64)<<40)
        pal=np.zeros((n,8),np.int16); pal[:,0]=a0; pal[:,1]=a1
        for i in range(2,8): pal[:,i]=((a0*(8-i)+a1*(i-2))//6)
        A=np.zeros((n,16),np.uint8)
        for i in range(16):
            s=((bits>>(3*i))&7).astype(np.intp)
            v=pal[np.arange(n),s].astype(np.uint8)
            v=np.where((a0<=a1)&(s==7),0,v); v=np.where((a0>a1)&(s==0),255,v)
            A[:,i]=v
    else:
        a=blk[:,:8].reshape(n,8)
        A=np.stack([a[:,1]&15,a[:,1]>>4,a[:,0]&15,a[:,0]>>4,
                    a[:,3]&15,a[:,3]>>4,a[:,2]&15,a[:,2]>>4,
                    a[:,5]&15,a[:,5]>>4,a[:,4]&15,a[:,4]>>4,
                    a[:,7]&15,a[:,7]>>4,a[:,6]&15,a[:,6]>>4],-1)*17
    rgb,_=dec_dxt1(np.ascontiguousarray(blk[:,8:]),w,h)
    return rgb,A.reshape(h,w)

def make_dds(fmt,w,h,pixels):
    fourcc={FMT_DXT1:b'DXT1',FMT_DXT3:b'DXT3',FMT_DXT5:b'DXT5'}.get(fmt)
    hdr=bytearray(128); hdr[0:4]=b'DDS '
    struct.pack_into('<I',hdr,4,124)
    struct.pack_into('<I',hdr,8,0x1007 | (0x80000 if fourcc else 0x8))
    struct.pack_into('<I',hdr,12,h)
    struct.pack_into('<I',hdr,16,w)
    if fourcc:
        struct.pack_into('<I',hdr,20,(w+3)//4*8 if fmt==FMT_DXT1 else (w+3)//4*16)
        struct.pack_into('<I',hdr,76,0x4)
        hdr[80:84]=fourcc
    else:
        struct.pack_into('<I',hdr,20,w*4)
        struct.pack_into('<I',hdr,76,0x41)
        struct.pack_into('<I',hdr,88,32)
        struct.pack_into('<I',hdr,92,0x00ff0000)
        struct.pack_into('<I',hdr,96,0x0000ff00)
        struct.pack_into('<I',hdr,100,0x000000ff)
        struct.pack_into('<I',hdr,104,0xff000000)
    struct.pack_into('<I',hdr,108,0x1000)
    return bytes(hdr)+bytes(pixels)

def iter_textures(data):
    for typ,off,size in parse_chunks(data,0,len(data)):
        if typ!=0x1 or size<=HDR: continue
        b0=off+12
        body=data[b0:b0+size]
        if len(body)<HDR: continue
        fmt,w,h=struct.unpack_from('<IHH',body,76)
        mips=body[85]
        name=body[8:40].split(NULLBYTE)[0].decode('cp1252','replace')
        expect=sum(lvl_size(fmt,max(1,w>>i),max(1,h>>i)) for i in range(mips))
        payload=len(body)-HDR
        yield name,fmt,w,h,mips,body[HDR:],expect,payload

def export_txd(data,outdir):
    os.makedirs(outdir,exist_ok=True)
    n=0
    for name,fmt,w,h,mips,px,expect,payload in iter_textures(data):
        try:
            if payload not in (expect,expect+28): n+=1; continue
            if fmt==FMT_A8R8G8B8:
                arr=np.frombuffer(px[:w*h*4],dtype=np.uint8).reshape(h,w,4)
                Image.fromarray(arr,'RGBA').save(os.path.join(outdir,name+'.png'))
            else:
                if fmt==FMT_DXT1: rgb,a=dec_dxt1(px[:lvl_size(fmt,w,h)],w,h)
                else: rgb,a=dec_dxt35(px[:lvl_size(fmt,w,h)],w,h,fmt==FMT_DXT5)
                Image.fromarray(np.dstack([rgb,a]),'RGBA').save(os.path.join(outdir,name+'.png'))
            n+=1
        except Exception as e:
            print('  tex-skip %s: %s'%(name,e))
    return n

def cmd_export(root,outroot):
    total=fail=0
    for dp,dn,fn in os.walk(root):
        for f in fn:
            if not f.lower().endswith('.txd'): continue
            p=os.path.join(dp,f)
            rel=os.path.relpath(p,root)
            sub=os.path.join(outroot,os.path.splitext(rel)[0])
            try:
                total+=export_txd(open(p,'rb').read(),sub)
            except Exception as e:
                import traceback; fail+=1
                traceback.print_exc()
                print('[FAIL]',rel,e)
    print('exported %d dds, %d failed files'%(total,fail))


def cmd_import(builtdir,gamedir):
    copied=missing=0
    for dp,dn,fn in os.walk(builtdir):
        for f in fn:
            if not f.lower().endswith('.txd'): continue
    # second pass after build completes
    for dp,dn,fn in os.walk(builtdir):
        for f in fn:
            if not f.lower().endswith('.txd'): continue
            src=os.path.join(dp,f)
            rel=os.path.relpath(src,builtdir)
            dst=os.path.join(gamedir,rel)
            if os.path.exists(dst):
                shutil.copy2(src,dst); copied+=1
            else:
                missing+=1
                print('[NOMATCH]',rel)
    print('imported %d, no-match %d'%(copied,missing))

def main():
    if len(sys.argv)<2: print(__doc__); sys.exit(1)
    if sys.argv[1]=='--import':
        cmd_import(sys.argv[2],sys.argv[3]); sys.exit(0)
    if sys.argv[1]=='--export':
        cmd_export(sys.argv[2],sys.argv[3])
    else:
        print(__doc__)

if __name__=='__main__':
    main()
