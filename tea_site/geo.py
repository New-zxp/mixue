import math
import numpy as np

def gcj_to_wgs(lon, lat):
    """Approximate inverse; preserve source GCJ separately. Not surveying grade."""
    x,y=lon-105,lat-35
    a=6378245.0; ee=0.006693421622965943
    dl=-100+2*x+3*y+.2*y*y+.1*x*y+.2*math.sqrt(abs(x))
    dl+=(20*math.sin(6*x*math.pi)+20*math.sin(2*x*math.pi))*2/3
    dl+=(20*math.sin(y*math.pi)+40*math.sin(y/3*math.pi))*2/3
    dl+=(160*math.sin(y/12*math.pi)+320*math.sin(y*math.pi/30))*2/3
    dn=300+x+2*y+.1*x*x+.1*x*y+.1*math.sqrt(abs(x))
    dn+=(20*math.sin(6*x*math.pi)+20*math.sin(2*x*math.pi))*2/3
    dn+=(20*math.sin(x*math.pi)+40*math.sin(x/3*math.pi))*2/3
    dn+=(150*math.sin(x/12*math.pi)+300*math.sin(x/30*math.pi))*2/3
    rad=lat*math.pi/180; magic=1-ee*math.sin(rad)**2
    dl=dl*180/((a*(1-ee)/(magic*math.sqrt(magic)))*math.pi)
    dn=dn*180/(a/math.sqrt(magic)*math.cos(rad)*math.pi)
    return lon-dn, lat-dl

SX=111195.08*math.cos(math.radians(41.8)); SY=111195.08
def xy(points):
    a=np.asarray(points,dtype=float).reshape(-1,2)
    return (a-[123.4,41.8])*[SX,SY]

def lonlat(points):
    return np.asarray(points)/[SX,SY]+[123.4,41.8]
