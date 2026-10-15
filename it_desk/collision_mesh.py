"""Bake negative STL scales into vertices; DART requires positive mesh scales.
Only derived collision assets are written. Upstream mesh files remain unchanged.
"""
from pathlib import Path
import hashlib,struct,re
import numpy as np
DTYPE=np.dtype([('normal','<f4',(3,)),('vertices','<f4',(3,3)),('attribute','<u2')])

def read_triangles(data):
    if len(data)>=84:
        count=struct.unpack_from('<I',data,80)[0]
        if len(data)==84+count*50:
            return np.frombuffer(data,dtype=DTYPE,count=count,offset=84)['vertices'].astype(np.float64)
    # ASCII STL fallback. Each facet contains exactly three vertex lines.
    vertices=re.findall(rb'\bvertex\s+([^\r\n]+)',data)
    if not vertices or len(vertices)%3:raise ValueError('Invalid binary/ASCII STL')
    a=np.array([[float(v) for v in line.split()] for line in vertices],dtype=np.float64)
    return a.reshape(-1,3,3)

def positive_collision_mesh(path,scale,cache):
    path=Path(path);scale=np.asarray(scale,dtype=np.float64)
    if scale.shape!=(3,) or not np.isfinite(scale).all() or np.any(scale==0):raise ValueError('Invalid collision mesh scale')
    if np.all(scale>0):return path,scale
    if path.suffix.lower()!='.stl':raise ValueError('Negative collision scale requires STL: '+str(path))
    data=path.read_bytes();key=hashlib.sha256(data+scale.astype('<f8').tobytes()+b'bake-v1').hexdigest()[:20]
    cache=Path(cache);cache.mkdir(parents=True,exist_ok=True);out=cache/(path.stem+'_'+key+'.stl')
    if not out.exists():
        triangles=read_triangles(data)*scale
        if not np.isfinite(triangles).all():raise ValueError('Nonfinite STL coordinates')
        # A reflection reverses handedness: swap two vertices to retain outward faces.
        if np.prod(scale)<0:triangles=triangles[:,[0,2,1],:]
        normals=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])
        lengths=np.linalg.norm(normals,axis=1);good=lengths>0;normals[good]/=lengths[good,None]
        faces=np.zeros(len(triangles),dtype=DTYPE);faces['vertices']=triangles;faces['normal']=normals
        out.write_bytes(b'PAI derived collision STL; mirrored vertices; positive scale'.ljust(80,b' ')+struct.pack('<I',len(faces))+faces.tobytes())
    return out,np.ones(3)
