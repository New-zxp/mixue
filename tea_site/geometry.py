import numpy as np
from .geo import xy

def inside_ring(points,ring):
    """Vectorized ray casting. Points on edges use the ray-casting half-open convention."""
    p=np.asarray(points);r=xy(ring);inside=np.zeros(len(p),dtype=bool)
    x,y=p[:,0],p[:,1];xj,yj=r[-1]
    for xi,yi in r:
        crosses=((yi>y)!=(yj>y))&(x<(xj-xi)*(y-yi)/(yj-yi+1e-30)+xi)
        inside^=crosses
        xj,yj=xi,yi
    return inside

def boundary_mask(points,boundaries):
    result=np.zeros(len(points),dtype=bool)
    for b in boundaries.values():
        for ring in b.get('rings',[]):result|=inside_ring(points,ring)
    return result
