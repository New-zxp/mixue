# 本地街道地图

街道图随项目提供，位于 `data/maps/shenyang-streets.pmtiles`。浏览器按需读取本地服务的数据块，不从外部地图服务器下载瓦片，无需 Key。空白图只展示边界和勾选的门店、设施。

底图来自 Protomaps OpenStreetMap 向量地图，保留地图中的 OpenStreetMap 和 Protomaps 署名。来源信息、范围和校验值见 `data/maps/manifest.json`。

来源：https://data.source.coop/protomaps/openstreetmap/v4.pmtiles

OpenStreetMap 数据许可：https://www.openstreetmap.org/copyright

地图包含已有范围及缩放层级；放大超过原始细节等级不会增加新道路信息。应用保持沈阳九区范围。PMTiles 和 Leaflet 的第三方许可保留在 `static/vendor/`。
