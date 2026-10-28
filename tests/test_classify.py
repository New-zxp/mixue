from tea_site.classify import classify

def test_query_hit_does_not_override_real_type():
    p={'name':'某购物中心停车场','type':'交通设施服务;停车场;公共停车场','query_hits':['mall']}
    assert classify(p,'蜜雪冰城')['categories']==['review']

def test_coffee_is_separate_and_target_requires_food_type():
    assert classify({'name':'瑞幸咖啡','type':'餐饮服务;咖啡厅;咖啡厅'},'蜜雪冰城')['categories']==['coffee']
    assert classify({'name':'蜜雪冰城','type':'餐饮服务;冷饮店;冷饮店'},'蜜雪冰城')['categories']==['target']
    assert classify({'name':'蜜雪冰城仓库','type':'公司企业;公司;公司'},'蜜雪冰城')['categories']==['review']

def test_actual_mall_and_school_are_demand():
    assert classify({'name':'商场','type':'购物服务;商场;购物中心'},'蜜雪冰城')['categories']==['mall']
    assert classify({'name':'大学','type':'科教文化服务;学校;高等院校'},'蜜雪冰城')['categories']==['school']
