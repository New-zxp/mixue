"""Conservative, inspectable classification; query keywords are not labels."""
import re
VERSION='type-name-v2'
TEA_BRANDS=['蜜雪冰城','霸王茶姬','茶百道','喜茶','古茗','沪上阿姨','甜啦啦','益禾堂','书亦烧仙草','一点点','奈雪','茶颜悦色','CoCo','都可','柠季','LINLEE','快乐柠檬','阿水大杯茶','悸动烧仙草','茶理宜世','茉莉奶白']
COFFEE_BRANDS=['瑞幸','星巴克','库迪','幸运咖','Manner','Tims','NOWWA','挪瓦']
def classify(p,brand):
    name=str(p.get('name',''));typ=str(p.get('type',''));paths=[s.split(';') for s in typ.split('|')]
    food=any(s and s[0]=='餐饮服务' for s in paths)
    if brand in name and food:cats=['target'];reason='品牌名称与餐饮类别共同匹配'
    elif food and (any(b.lower() in name.lower() for b in TEA_BRANDS) or re.search('奶茶|茶饮|鲜奶茶|柠檬茶',name)):
        cats=['competitor'];reason='餐饮类别与茶饮名称共同匹配'
    elif food and ('咖啡厅' in typ or any(b.lower() in name.lower() for b in COFFEE_BRANDS)):
        cats=['coffee'];reason='咖啡类别，默认不计入茶饮竞争'
    else:
        checks={'residential':lambda s:len(s)>2 and s[0]=='商务住宅' and s[2]=='住宅小区',
                'office':lambda s:len(s)>2 and s[0]=='商务住宅' and s[2]=='商务写字楼',
                'school':lambda s:len(s)>1 and s[:2]==['科教文化服务','学校'],
                'mall':lambda s:len(s)>1 and s[:2]==['购物服务','商场'],
                'metro':lambda s:len(s)>1 and s[:2]==['交通设施服务','地铁站'],
                'bus':lambda s:len(s)>1 and s[:2]==['交通设施服务','公交车站']}
        cats=[c for c,check in checks.items() if any(check(s) for s in paths)]
        reason='按返回POI类别匹配' if cats else '类别/名称不足以确认，不参与计算'
    if not cats:cats=['review']
    detected=brand if 'target' in cats else next((b for b in TEA_BRANDS+COFFEE_BRANDS if b.lower() in name.lower()),'独立/未识别品牌')
    return {'categories':cats,'brand':detected,'classification_reason':reason,'classification_version':VERSION}
def clean_record(row,brand):
    result=dict(row);result.update(classify(row,brand));return result
