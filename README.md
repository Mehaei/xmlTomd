# xmlTomd

## 说明

* 支持抓取单篇微信文章并下载图片资源及转为github page（jeklly）配套的markdown文章
* 执行将cnblogs（博客园）备份的xml文章下载图片资源及转为github page（jeklly）配套的markdown文章

## 使用

#### 执行完成后文章会在`blog_root` /_post中（文章名为 md5（标题+日期）），下载对应的图片会在`blog_root`/image/`md5`中。

1. 导入cnblogs xml文章

```python
xml_files = ["cnblogs_blog_mswei.20250728163812.xml"]
xml_crawler = XmlArticleCrawler(xml_files, download_images=True)
# 获取每篇文章分类, 也就是文章头中的categories,如果不需要则不需要获取,函数中的分类替换为自己的分类,在博客管理后台找一下分类请求复制下来就行。
# xml_crawler.get_category()
# 开始转换文章，并下载其中的图片
xml_crawler.crawl()
```

2. 抓取微信公众号文章

```python
# 文章id，比如：[https://mp.weixin.qq.com/s/t27RQEsrYJzjxEJr4PWgMA], 就填写 t27RQEsrYJzjxEJr4PWgMA
pid_list = ["C75Haa47Oeq5DsPwA0BMSw", "t27RQEsrYJzjxEJr4PWgMA"]
wx_crawler = WeChatArticleCrawler(blog_root="../source", download_images=True)
# 下载文章并转为md格式, 同时会下载文章封面和其中的配图
wx_crawler.crawl_batch(pid_list)
```

```

```
