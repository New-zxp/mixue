import numpy as np
from scipy.spatial.distance import cdist
from .geo import xy,lonlat

def kde(pois,bandwidth=800):
    """Gaussian intensity in shops/km² on fixed metre cells; no population correction."""
    coords=xy([[p['lon'],p['lat']] for p in pois if 'target' in p['categories']])
    if not len(coords):return {'bandwidth_m':bandwidth,'cells':[],'max':0}
    low=coords.min(axis=0)-2*bandwidth;high=coords.max(axis=0)+2*bandwidth
    step=max(250,float(np.max(high-low))/60)
    xx,yy=np.meshgrid(np.arange(low[0],high[0]+step,step),np.arange(low[1],high[1]+step,step))
    grid=np.column_stack([xx.ravel(),yy.ravel()])
    density=np.exp(-.5*(cdist(grid,coords)/bandwidth)**2).sum(axis=1)/(2*np.pi*bandwidth**2)*1e6
    cells=[{'lon':float(lon),'lat':float(lat),'value':float(value)} for (lon,lat),value in zip(lonlat(grid),density)]
    return {'bandwidth_m':bandwidth,'step_m':step,'cells':cells,'max':float(density.max()),'unit':'家/平方公里（样本核密度强度）'}
