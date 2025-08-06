# -*- coding: utf-8 -*-

# @Author: 胖胖很瘦
# @Date: 2025-07-28 16:57:12
# @LastEditors: 胖胖很瘦
# @LastEditTime: 2025-08-06 10:44:00

# -*- coding: utf-8 -*-
# Unified Markdown Crawler: WeChat + XML (for Jekyll)

import os
import re
import hashlib
import requests
import traceback
import random
import bs4
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from datetime import datetime
import time
# from lxml import etree
import xml.etree.ElementTree as ET


HEADER = """---
layout:     post
title:      "{title}"
subtitle:   
date:       {date}
author:     {author}
thumbnail:  {thumbnail}
catalog: true
categories: {categories}
original_url: {url}
tags:
{tags_yaml}
---
"""

class BaseMarkdownCrawler:
    """
    公共基类：提供下载、ID 生成、保存 markdown、图片目录管理等功能。
    """
    def __init__(self, blog_root=".", download_images=True, max_retries=10):
        self.blog_root = blog_root
        self.download_images = download_images
        self.max_retries = max_retries
        self.posts_dir = os.path.join(blog_root, "_posts")
        self.images_dir = os.path.join(blog_root, "images")
        os.makedirs(self.posts_dir, exist_ok=True)
        os.makedirs(self.images_dir, exist_ok=True)

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/114.0 Safari/537.36"
        })

    def generate_short_id(self, text):
        md5_val = hashlib.md5(text.encode("utf-8")).hexdigest()
        return md5_val[:8]

    def get_proxies(self):
        ip = "http://127.0.0.1:7890"
        return {"http": ip, "https": ip}


    def fetch_article(self, url, timeout=10):
        for attempt in range(self.max_retries):
            try:
                proxies = self.get_proxies()
                print("Fetching %s with proxy %s" % (url, proxies))
                resp = self.session.get(url, proxies=proxies, timeout=timeout)
                resp.raise_for_status()
                return resp.text
            except Exception as e:
                print(f"Retry {attempt+1}/{self.max_retries} for {url} ({e})")
                time.sleep(1)
        raise Exception(f"Failed to fetch {url} after {self.max_retries} retries")

    def download_file(self, url, dest_path):
        """下载文件，失败自动重试"""
        for attempt in range(self.max_retries):
            try:
                proxies = self.get_proxies()
                resp = self.session.get(url, proxies=proxies, timeout=10)
                resp.raise_for_status()
                with open(dest_path, "wb") as f:
                    f.write(resp.content)
                return True
            except Exception as e:
                print(f"Retry {attempt+1}/{self.max_retries} for {url} ({e})")
                time.sleep(1)
        print(f"Failed to download after {self.max_retries} retries: {url}")
        return False

    def save_markdown(self, short_id, content, date):
        filename = f"{date}-{short_id}.md"
        filepath = os.path.join(self.posts_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Saved: {filepath}")

    def download_images_and_replace(self, soup_or_html, article_img_dir, article_id):
        """
        通用图片下载：支持 BeautifulSoup 或 HTML 字符串。
        图片按 1.png, 2.png 命名，替换 src。
        """
        if isinstance(soup_or_html, (BeautifulSoup, bs4.element.Tag)):
            img_tags = soup_or_html.find_all("img")
            for idx, img in enumerate(img_tags, start=1):
                os.makedirs(article_img_dir, exist_ok=True)
                img_url = img.get("data-src") or img.get("src")
                if not img_url:
                    continue
                filename = f"{idx}.png"
                local_path = os.path.join(article_img_dir, filename)
                if self.download_images:
                    self.download_file(img_url, local_path)
                img["src"] = f"/images/{article_id}/{filename}"
            return soup_or_html
        else:
            # HTML 字符串处理（用于 XML 内容）
            def repl(m):
                os.makedirs(article_img_dir, exist_ok=True)
                idx = repl.counter + 1
                repl.counter += 1
                img_url = m.group(1)
                filename = f"{idx}.png"
                local_path = os.path.join(article_img_dir, filename)
                if self.download_images:
                    self.download_file(img_url, local_path)
                return f'src="/images/{article_id}/{filename}"'
            repl.counter = 0
            return re.sub(r'src=["\'](.*?)["\']', repl, soup_or_html)


class WeChatArticleCrawler(BaseMarkdownCrawler):
    """保持原微信爬虫功能，继承公共逻辑"""
    def parse_title(self, soup):
        tag = soup.find("h1", class_="rich_media_title")
        return tag.get_text(strip=True) if tag else "Untitled"

    def parse_date_and_cate(self, soup):
        albums = []
        date_string = datetime.now().strftime("%Y-%m-%d")
        for s in soup.find_all("script"):
            js_string = s.string
            if js_string and "createTime" in js_string:
                m = re.search(r"createTime\s*=\s*'([\d\-: ]+)'", js_string)
                if m:
                    date_string = m.group(1).split()[0]
            if js_string and " album_info_list " in js_string:
                # 匹配每个对象
                obj_pattern = re.compile(r"\{\s*(.*?)\s*\}", re.S)
                # 匹配 key: 'value'
                field_pattern = re.compile(r"(\w+):\s*'([^']*)'")

                for obj_match in obj_pattern.findall(js_string):
                    fields = dict(field_pattern.findall(obj_match))
                    # 清洗值：替换 &amp;，去掉 *1 表达式影响
                    clean_fields = {}
                    for k, v in fields.items():
                        v = v.replace("&amp;", "&").strip()
                        clean_fields[k] = v
                    if "albumId" in clean_fields and "title" in clean_fields:
                        albums.append(clean_fields["title"])

                # print(albums)
        return date_string, albums

    def parse_thumbnail_url(self, soup):
        tag = soup.find("meta", {"property": "og:image"})
        return tag["content"] if tag and tag.get("content") else "/images/default-post-thumbnail.png"

    def parse_author(self, soup):
        tag = soup.find("meta", {"name": "author"})
        return tag["content"] if tag and tag.get("content") else "胖胖不胖"

    def parse_category(self, soup):
        tags = []
        for span in soup.select("span.wx_tap_link.js_album_directory__name"):
            text = span.get_text(strip=True)
            if text:
                tags.append(text.replace("· 目录", "").strip())
        if not tags:
            for span in soup.select("span.article-tag__item"):
                text = span.get_text(strip=True)
                if text:
                    tags.append(text)
        return list(dict.fromkeys(tags))

    def extract_content_div(self, soup):
        content_div = soup.find("div", id="js_content")
        if not content_div:
            return None
        # 清理 span leaf 和 pre 逻辑（保持原逻辑）
        for span in content_div.select("li > section > span[leaf]"):
            raw_text = span.get_text()
            cleaned = re.sub(r"(^\s*)\d+\.\s*", r"\1", raw_text)
            cleaned = re.sub(r"(^\s*)•\s*", r"\1", cleaned)
            span.string = cleaned
        for pre in content_div.find_all("pre"):
            inner_text = pre.get_text().replace("\n", "").replace("\r", "").strip()
            if inner_text == "":
                pre.decompose()
                continue
            codes = pre.find_all("code")
            if len(codes) == 0:
                pre.name = "p"
            elif len(codes) > 1:
                combined = "\n".join(code.get_text() for code in codes)
                new_code = soup.new_tag("code")
                new_code.string = combined
                pre.clear()
                pre.append(new_code)
        return content_div

    def html_to_markdown(self, soup):
        return md(str(soup), heading_style="ATX", code_language_detection=True)

    def generate_front_matter(self, title, date, url, thumbnail, category, author):
        tags_yaml = "\n".join(f"    - {tag}" for tag in (category or ["Python"]))
        return HEADER.format(
            title=title, date=date, url=url, thumbnail=thumbnail,
            tags_yaml=tags_yaml, author=author, categories=(category[:1] or ["微信公众号"])[0]
        )

    def crawl_single(self, url):
        html = self.fetch_article(url)
        soup = BeautifulSoup(html, "html.parser")
        title = self.parse_title(soup)
        date_string, category = self.parse_date_and_cate(soup)
        thumb_url = self.parse_thumbnail_url(soup)
        author = self.parse_author(soup)
        # category = self.parse_category(soup)
        # print(category)
        content_div = self.extract_content_div(soup)
        if not content_div:
            print(f"Failed to parse article: {url}")
            return
        short_id = self.generate_short_id(f"{title}-{date_string}")
        article_img_dir = os.path.join(self.images_dir, short_id)
        thumbnail_path = f"/images/{short_id}/thumbnail.png" if thumb_url else ""
        if thumb_url and self.download_images:
            os.makedirs(article_img_dir, exist_ok=True)
            self.download_file(thumb_url, os.path.join(article_img_dir, "thumbnail.png"))
        self.download_images_and_replace(content_div, article_img_dir, short_id)
        markdown_body = self.html_to_markdown(content_div)
        markdown_content = self.generate_front_matter(title, date_string, url, thumbnail_path, category, author) + "\n" + markdown_body
        self.save_markdown(short_id, markdown_content, date_string)

    def crawl_batch(self, pid_list):
        base_url = "https://mp.weixin.qq.com/s/{pid}"
        for pid in pid_list:
            try:
                url = base_url.format(pid=pid)
                self.crawl_single(url)
            except Exception:
                print(f"Failed to crawl {url}: {traceback.format_exc()}")


class XmlArticleCrawler(BaseMarkdownCrawler):
    """将博客园 XML 文件中的文章转换为 Markdown，下载资源"""
    def __init__(self, xml_files, **kwargs):
        super().__init__(**kwargs)
        self.xml_files = xml_files
        self.CATEGORIES = {'https://www.cnblogs.com/mswei/p/9988197.html': ['Django'], 'https://www.cnblogs.com/mswei/p/9988084.html': ['Django'], 'https://www.cnblogs.com/mswei/p/9442097.html': ['Django'], 'https://www.cnblogs.com/mswei/p/9441593.html': ['Django'], 'https://www.cnblogs.com/mswei/p/15568561.html': ['docker', 'Keycloak'], 'https://www.cnblogs.com/mswei/p/11981368.html': ['docker'], 'https://www.cnblogs.com/mswei/p/12073942.html': ['docker', 'python高级'], 'https://www.cnblogs.com/mswei/p/11849418.html': ['docker', 'mac-python3环境搭建'], 'https://www.cnblogs.com/mswei/p/11691009.html': ['docker', 'linux'], 'https://www.cnblogs.com/mswei/p/10365613.html': ['docker'], 'https://www.cnblogs.com/mswei/p/10365407.html': ['docker'], 'https://www.cnblogs.com/mswei/p/10365226.html': ['docker'], 'https://www.cnblogs.com/mswei/p/10364635.html': ['docker'], 'https://www.cnblogs.com/mswei/p/10364468.html': ['docker'], 'https://www.cnblogs.com/mswei/p/10406335.html': ['java'], 'https://www.cnblogs.com/mswei/p/14213448.html': ['js'], 'https://www.cnblogs.com/mswei/p/10335394.html': ['js'], 'https://www.cnblogs.com/mswei/p/10009191.html': ['js'], 'https://www.cnblogs.com/mswei/p/15149018.html': ['linux'], 'https://www.cnblogs.com/mswei/p/12160845.html': ['linux', 'Mongo'], 'https://www.cnblogs.com/mswei/p/12132232.html': ['linux'], 'https://www.cnblogs.com/mswei/p/11918484.html': ['linux', 'mac-python3环境搭建'], 'https://www.cnblogs.com/mswei/p/11643586.html': ['linux'], 'https://www.cnblogs.com/mswei/p/10572473.html': ['linux'], 'https://www.cnblogs.com/mswei/p/10368547.html': ['linux'], 'https://www.cnblogs.com/mswei/p/10245992.html': ['linux'], 'https://www.cnblogs.com/mswei/p/11760448.html': ['mac-python3环境搭建', 'sublime'], 'https://www.cnblogs.com/mswei/p/10881542.html': ['mac-python3环境搭建'], 'https://www.cnblogs.com/mswei/p/12769441.html': ['Mongo', 'python高级'], 'https://www.cnblogs.com/mswei/p/11692177.html': ['Mongo'], 'https://www.cnblogs.com/mswei/p/11691292.html': ['Mongo'], 'https://www.cnblogs.com/mswei/p/9683367.html': ['Mongo', 'python高级'], 'https://www.cnblogs.com/mswei/p/13044162.html': ['PostgreSQL'], 'https://www.cnblogs.com/mswei/p/11189916.html': ['pyqt5'], 'https://www.cnblogs.com/mswei/p/14761053.html': ['python高级', 'python爬虫'], 'https://www.cnblogs.com/mswei/p/14668360.html': ['python高级'], 'https://www.cnblogs.com/mswei/p/14103539.html': ['python高级', 'python爬虫'], 'https://www.cnblogs.com/mswei/p/13970404.html': ['python高级', 'python基础'], 'https://www.cnblogs.com/mswei/p/11951609.html': ['python高级'], 'https://www.cnblogs.com/mswei/p/11951181.html': ['python高级'], 'https://www.cnblogs.com/mswei/p/11926290.html': ['python高级'], 'https://www.cnblogs.com/mswei/p/11856258.html': ['python高级'], 'https://www.cnblogs.com/mswei/p/11653471.html': ['python高级'], 'https://www.cnblogs.com/mswei/p/10006076.html': ['python高级'], 'https://www.cnblogs.com/mswei/p/9370238.html': ['python高级'], 'https://www.cnblogs.com/mswei/p/9261859.html': ['python高级'], 'https://www.cnblogs.com/mswei/p/9250690.html': ['python高级'], 'https://www.cnblogs.com/mswei/p/11598340.html': ['python基础'], 'https://www.cnblogs.com/mswei/p/9393957.html': ['python基础'], 'https://www.cnblogs.com/mswei/p/9296875.html': ['python基础'], 'https://www.cnblogs.com/mswei/p/9296379.html': ['python基础'], 'https://www.cnblogs.com/mswei/p/9292134.html': ['python基础'], 'https://www.cnblogs.com/mswei/p/9290363.html': ['python基础'], 'https://www.cnblogs.com/mswei/p/9286833.html': ['python基础'], 'https://www.cnblogs.com/mswei/p/9286151.html': ['python基础'], 'https://www.cnblogs.com/mswei/p/9283546.html': ['python基础'], 'https://www.cnblogs.com/mswei/p/9283417.html': ['python基础'], 'https://www.cnblogs.com/mswei/p/9283386.html': ['python基础'], 'https://www.cnblogs.com/mswei/p/9283297.html': ['python基础'], 'https://www.cnblogs.com/mswei/p/9356265.html': ['python经典题'], 'https://www.cnblogs.com/mswei/p/9346802.html': ['python经典题'], 'https://www.cnblogs.com/mswei/p/9346653.html': ['python经典题'], 'https://www.cnblogs.com/mswei/p/15568488.html': ['python爬虫'], 'https://www.cnblogs.com/mswei/p/15568461.html': ['python爬虫', '微信公众号'], 'https://www.cnblogs.com/mswei/p/14168553.html': ['python爬虫'], 'https://www.cnblogs.com/mswei/p/12175505.html': ['python爬虫'], 'https://www.cnblogs.com/mswei/p/12174839.html': ['python爬虫'], 'https://www.cnblogs.com/mswei/p/11653504.html': ['python爬虫'], 'https://www.cnblogs.com/mswei/p/11602838.html': ['python爬虫'], 'https://www.cnblogs.com/mswei/p/11232393.html': ['python爬虫'], 'https://www.cnblogs.com/mswei/p/9835370.html': ['python爬虫'], 'https://www.cnblogs.com/mswei/p/9405260.html': ['python爬虫'], 'https://www.cnblogs.com/mswei/p/9404846.html': ['python爬虫'], 'https://www.cnblogs.com/mswei/p/9392530.html': ['python爬虫'], 'https://www.cnblogs.com/mswei/p/9361917.html': ['python爬虫'], 'https://www.cnblogs.com/mswei/p/9344685.html': ['python爬虫'], 'https://www.cnblogs.com/mswei/p/9339649.html': ['python爬虫'], 'https://www.cnblogs.com/mswei/p/9337987.html': ['python爬虫'], 'https://www.cnblogs.com/mswei/p/9337936.html': ['python爬虫'], 'https://www.cnblogs.com/mswei/p/9337845.html': ['python爬虫'], 'https://www.cnblogs.com/mswei/p/11956452.html': ['redis'], 'https://www.cnblogs.com/mswei/p/12767754.html': ['shell'], 'https://www.cnblogs.com/mswei/p/9965456.html': ['shell'], 'https://www.cnblogs.com/mswei/p/10558708.html': ['sublime'], 'https://www.cnblogs.com/mswei/p/10396812.html': ['tomcat'], 'https://www.cnblogs.com/mswei/p/10008504.html': ['tornado'], 'https://www.cnblogs.com/mswei/p/12145659.html': ['爆笑时刻'], 'https://www.cnblogs.com/mswei/p/11851000.html': ['爆笑时刻'], 'https://www.cnblogs.com/mswei/p/12103753.html': ['搭建在线视频网站'], 'https://www.cnblogs.com/mswei/p/12103700.html': ['搭建在线视频网站'], 'https://www.cnblogs.com/mswei/p/12103650.html': ['搭建在线视频网站'], 'https://www.cnblogs.com/mswei/p/12103518.html': ['搭建在线视频网站'], 'https://www.cnblogs.com/mswei/p/14180404.html': ['微信公众号'], 'https://www.cnblogs.com/mswei/p/12195576.html': ['微信公众号']}

    def sanitize_xml(self, xml_content):
        # 删除非法 XML 控制字符
        return re.sub(r"[\x00-\x08\x0B-\x0C\x0E-\x1F]", "", xml_content)

    def parse_items(self, xml_content):
        xml_content = self.sanitize_xml(xml_content)
        root = ET.fromstring(xml_content)
        # Atom: 每篇文章是 <entry>
        return root.findall(".//{http://www.w3.org/2005/Atom}entry")

    def extract_text(self, elem, tag, ns="{http://www.w3.org/2005/Atom}"):
        found = elem.find(ns + tag)
        return found.text.strip() if found is not None and found.text else ""

    def convert_item_to_markdown(self, item):
        ns = "{http://www.w3.org/2005/Atom}"
        title = self.extract_text(item, "title", ns)
        link_elem = item.find(f"{ns}link[@rel='alternate']")
        url = link_elem.get("href") if link_elem is not None else ""
        pub_date = self.extract_text(item, "published", ns)
        try:
            dt = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
            date = dt.strftime("%Y-%m-%d")
        except:
            date = datetime.now().strftime("%Y-%m-%d")
        author_elem = item.find(f"{ns}author/{ns}name")
        author = author_elem.text.strip() if author_elem is not None else "胖胖不胖"
        content_elem = item.find(f"{ns}content")
        description_html = content_elem.text if content_elem is not None else ""

        short_id = self.generate_short_id(f"{title}-{date}")
        article_img_dir = os.path.join(self.images_dir, short_id)
        # 下载并替换图片路径
        description_html = self.download_images_and_replace(description_html, article_img_dir, short_id)
        # 转 Markdown
        markdown_body = md(description_html, heading_style="ATX", code_language_detection=True)
        # YAML 头信息
        thumbnail_path = "/images/default-post-thumbnail.png"  # XML 没封面，使用默认
        categories = self.CATEGORIES.get(url, ["Cnblogs"])
        tags_yaml = "\n".join(f"    - {tag}" for tag in (categories or ["Python"]))

        front_matter = HEADER.format(
            title=title, date=date, url=url, thumbnail=thumbnail_path,
            tags_yaml=tags_yaml, author=author, categories=(categories[0:] if categories else ["Cnblogs"])[0]
        )
        markdown_content = front_matter + "\n" + markdown_body
        self.save_markdown(short_id, markdown_content, date)

    def get_category(self):
        categories = [
            {
                "categoryId": 1273381,
                "id": 1273381,
                "key": "1273381",
                "title": "Django",
                "visible": True,
                "order": None,
                "itemCount": 4,
                "selfItemCount": None,
                "childCount": 0,
                "descendantIds": [],
                "parentId":  None,
                "isLeaf": True,
                "children": []
            },
            {
                "categoryId": 1396784,
                "id": 1396784,
                "key": "1396784",
                "title": "docker",
                "visible": True,
                "order": None,
                "itemCount": 11,
                "selfItemCount": None,
                "childCount": 0,
                "descendantIds": [],
                "parentId":  None,
                "isLeaf": True,
                "children": []
            },
            {
                "categoryId": 1402308,
                "id": 1402308,
                "key": "1402308",
                "title": "java",
                "visible": True,
                "order": None,
                "itemCount": 1,
                "selfItemCount": None,
                "childCount": 0,
                "descendantIds": [],
                "parentId":  None,
                "isLeaf": True,
                "children": []
            },
            {
                "categoryId": 1392565,
                "id": 1392565,
                "key": "1392565",
                "title": "js",
                "visible": True,
                "order": None,
                "itemCount": 3,
                "selfItemCount": None,
                "childCount": 0,
                "descendantIds": [],
                "parentId":  None,
                "isLeaf": True,
                "children": []
            },
            {
                "categoryId": 2064019,
                "id": 2064019,
                "key": "2064019",
                "title": "Keycloak",
                "visible": True,
                "order": None,
                "itemCount": 1,
                "selfItemCount": None,
                "childCount": 0,
                "descendantIds": [],
                "parentId":  None,
                "isLeaf": True,
                "children": []
            },
            {
                "categoryId": 1322758,
                "id": 1322758,
                "key": "1322758",
                "title": "linux",
                "visible": True,
                "order": None,
                "itemCount": 10,
                "selfItemCount": None,
                "childCount": 0,
                "descendantIds": [],
                "parentId":  None,
                "isLeaf": True,
                "children": []
            },
            {
                "categoryId": 1466002,
                "id": 1466002,
                "key": "1466002",
                "title": "mac-python3环境搭建",
                "visible": True,
                "order": None,
                "itemCount": 4,
                "selfItemCount": None,
                "childCount": 0,
                "descendantIds": [],
                "parentId":  None,
                "isLeaf": True,
                "children": []
            },
            {
                "categoryId": 1304232,
                "id": 1304232,
                "key": "1304232",
                "title": "Mongo",
                "visible": True,
                "order": None,
                "itemCount": 5,
                "selfItemCount": None,
                "childCount": 0,
                "descendantIds": [],
                "parentId":  None,
                "isLeaf": True,
                "children": []
            },
            {
                "categoryId": 1780329,
                "id": 1780329,
                "key": "1780329",
                "title": "PostgreSQL",
                "visible": True,
                "order": None,
                "itemCount": 1,
                "selfItemCount": None,
                "childCount": 0,
                "descendantIds": [],
                "parentId":  None,
                "isLeaf": True,
                "children": []
            },
            {
                "categoryId": 1504115,
                "id": 1504115,
                "key": "1504115",
                "title": "pyqt5",
                "visible": True,
                "order": None,
                "itemCount": 1,
                "selfItemCount": None,
                "childCount": 0,
                "descendantIds": [],
                "parentId":  None,
                "isLeaf": True,
                "children": []
            },
            {
                "categoryId": 1245403,
                "id": 1245403,
                "key": "1245403",
                "title": "python高级",
                "visible": True,
                "order": None,
                "itemCount": 16,
                "selfItemCount": None,
                "childCount": 0,
                "descendantIds": [],
                "parentId":  None,
                "isLeaf": True,
                "children": []
            },
            {
                "categoryId": 1250376,
                "id": 1250376,
                "key": "1250376",
                "title": "python基础",
                "visible": True,
                "order": None,
                "itemCount": 13,
                "selfItemCount": None,
                "childCount": 0,
                "descendantIds": [],
                "parentId":  None,
                "isLeaf": True,
                "children": []
            },
            {
                "categoryId": 1259200,
                "id": 1259200,
                "key": "1259200",
                "title": "python经典题",
                "visible": True,
                "order": None,
                "itemCount": 3,
                "selfItemCount": None,
                "childCount": 0,
                "descendantIds": [],
                "parentId":  None,
                "isLeaf": True,
                "children": []
            },
            {
                "categoryId": 1250759,
                "id": 1250759,
                "key": "1250759",
                "title": "python爬虫",
                "visible": True,
                "order": None,
                "itemCount": 34,
                "selfItemCount": None,
                "childCount": 0,
                "descendantIds": [],
                "parentId":  None,
                "isLeaf": True,
                "children": []
            },
            {
                "categoryId": 1602829,
                "id": 1602829,
                "key": "1602829",
                "title": "redis",
                "visible": True,
                "order": None,
                "itemCount": 1,
                "selfItemCount": None,
                "childCount": 0,
                "descendantIds": [],
                "parentId":  None,
                "isLeaf": True,
                "children": []
            },
            {
                "categoryId": 1342475,
                "id": 1342475,
                "key": "1342475",
                "title": "shell",
                "visible": True,
                "order": None,
                "itemCount": 2,
                "selfItemCount": None,
                "childCount": 0,
                "descendantIds": [],
                "parentId":  None,
                "isLeaf": True,
                "children": []
            },
            {
                "categoryId": 1423204,
                "id": 1423204,
                "key": "1423204",
                "title": "sublime",
                "visible": True,
                "order": None,
                "itemCount": 2,
                "selfItemCount": None,
                "childCount": 0,
                "descendantIds": [],
                "parentId":  None,
                "isLeaf": True,
                "children": []
            },
            {
                "categoryId": 1401056,
                "id": 1401056,
                "key": "1401056",
                "title": "tomcat",
                "visible": True,
                "order": None,
                "itemCount": 1,
                "selfItemCount": None,
                "childCount": 0,
                "descendantIds": [],
                "parentId":  None,
                "isLeaf": True,
                "children": []
            },
            {
                "categoryId": 1348041,
                "id": 1348041,
                "key": "1348041",
                "title": "tornado",
                "visible": True,
                "order": None,
                "itemCount": 1,
                "selfItemCount": None,
                "childCount": 0,
                "descendantIds": [],
                "parentId":  None,
                "isLeaf": True,
                "children": []
            },
            {
                "categoryId": 1589641,
                "id": 1589641,
                "key": "1589641",
                "title": "爆笑时刻",
                "visible": True,
                "order": None,
                "itemCount": 2,
                "selfItemCount": None,
                "childCount": 0,
                "descendantIds": [],
                "parentId":  None,
                "isLeaf": True,
                "children": []
            },
            {
                "categoryId": 1621410,
                "id": 1621410,
                "key": "1621410",
                "title": "搭建在线视频网站",
                "visible": True,
                "order": None,
                "itemCount": 4,
                "selfItemCount": None,
                "childCount": 0,
                "descendantIds": [],
                "parentId":  None,
                "isLeaf": True,
                "children": []
            },
            {
                "categoryId": 1554329,
                "id": 1554329,
                "key": "1554329",
                "title": "微信公众号",
                "visible": True,
                "order": None,
                "itemCount": 4,
                "selfItemCount": None,
                "childCount": 0,
                "descendantIds": [],
                "parentId":  None,
                "isLeaf": True,
                "children": []
            }
        ]
        result = {}
        base_url = "https://www.cnblogs.com/mswei/category/{category_id}.html"
        for cat in categories:
            category_id = cat["categoryId"]
            category_name = cat["title"]
            url = base_url.format(category_id=category_id)

            print(f"Fetching category: {category_name} ({url})")
            html = self.fetch_article(url)

            soup = BeautifulSoup(html, "html.parser")
            links = soup.select("a.entrylistItemTitle")

            for a in links:
                href = a.get("href")
                if href not in result:
                    result[href] = []
                result[href].append(category_name)

        print(result)

    def crawl(self):
        for xml_file in self.xml_files:
            try:
                with open(xml_file, "r", encoding="utf-8") as f:
                    content = f.read()
                items = self.parse_items(content)
                print("post items lenth: ", len(items))
                for item in items:
                    self.convert_item_to_markdown(item)
            except Exception:
                print(f"Failed to process {xml_file}: {traceback.format_exc()}")


if __name__ == "__main__":
    # 示例：处理 XML
    xml_files = ["nes.xml"]
    xml_files = ["cnblogs_blog_mswei.20250728163812.xml"]
    xml_crawler = XmlArticleCrawler(xml_files, download_images=True)
    # xml_crawler.get_category()
    # xml_crawler.crawl()
    # 示例：处理微信文章
    pid_list = [
        "9ah9AKqPMfHtAqVlZbsG5w",
        "PaPEJj2RnQ6IFFl5ngSrTg",
        "WrkmXrQw77LFU3WqVxrNfw",
        "PLkCYQuicE5ZZNAZ0Gj5gw",
        "X71e24q3VoVu6ZCHoIVXgA",
        "TXjM9Ys56kR1W-bYC-nGUg",
        "KlDgythMgLHVECri0Z7u9g",
        "zs-i9Ht5tJkafR-RFunWWw",
        "gDIyi7FiyjQM54DCJhcXzg",
        "Q0M99A-EHIQWco3J2ODw2w",
        "-lQzHLBl4QkmEk7eFHwtqg",
        "0r8qq3YzSjHEFHmeRMVD0A",
        "0zd3t7k9CYcwTLevh0KFHw",
        "eB-cRmU1YRssMAfZI3GYlA",
        "-vTnQaIodbcZjejhhact6A",
        "_-ccswnewGADvH-OaB5HAw",
        "UXXdkI-Z4xSn2rW7ANOVgg",
        "yU2Q-kMnYM3lpbBvnPXO2w",
        "YBE3oA1_khz76yHBhdduTQ",
        "4CGivwc1X-YxNeRZUaoDMw",
        "TplEnSoxCC0rViBmoalIyg",
        "XLRAy1I2h-VjY6bix3Oetg",
        "v1fyySu504XMZgAObLdupQ",
        "_d7aVcsT5YV8G8HlbN1KwQ",
        "NOm5wmbRlLyWhpSE6YbsXA",
        "QDCW_XuswNPnuAXJFM9jjQ",
        "KTolHHe_PIGcZM3pbAzAFw",
        "bqet3NguhTqRXTKjvgmWIw",
        "oU-79mfcOl-Orr6rSmd4vA",
        "nH_LFNjKROZKZDMzDcfDjA",
        "8KM6pGYpEQFhXq7hvrsVpA",
        "q66XCApasYjqS8k5wlXsFg",
        "Nj8ges_iPfJ7JMNQAR8pqQ",
        "ZA0rMkp86L6pGkZ8p0F0QA",
        "hT-qs6Imc2umtG8QwjHP0w",
        "IlaMS-zUnTN1HgFSSLEkPg",
        "9Z0vOSxfAvXcqb7UTzWnEQ",
        "N0yCKY6bJlY2pOSeLmgf4g",
        "_jlDyc78z6MCVO21EFCnvg",
        "nhQAOcpOVKQl79PriWE4xg",
        "TwhG72Jwjse0-xfj5H0daQ",
        "uovTjGCqUwVvKJuCE2Ee-w",
        "u29AD9XvMfWHzKB6wtXv_A",
        "jsBcjtDnaA6VwYJH8bOXBw",
        "nvKzEmOc9ohp0Yvt-usQ1g",
        "vGNjh4F7e6bK9AGHpVRtPA",
        "xO_tST9bATh1uzU3UVXTQA",
        "dLh2BWpdAbAYLC6-qGsVeg",
        "PUtAsSDfOaPb_rR0SAS4BQ",
        "vyECsdYOwwtNuq0rYp_UjA",
        "dfiYqCINmgGge0lZlRHxrQ",
        "PpeFiSsW5GcEdqSaLWXblA",
        "HbqPdCGTDh24hqwFBX5ROA",
        "ENdQ6B_-kATkJLGIWAVQKQ",
        "92a9WIowbuYWKNz1Bvl9Hw",
        "XeGjjol4AbCDaAe_rOXO3Q",
        "uFHaQSZQx4TV-Yc6GcmXrw",
        "p5SqypdFnch3_qZUvoyPlQ",
        "_GOmFPobsS1yEIoY-REE6A",
        "F5m3mvaql24jQlpiSToeMw",
        "hc0F48VDRwTISZm0402XyQ",
        "Fuj78fp331HEk-W5fIqCRA",
        "F_JH7eEOkU5_0Ni5Tf-tLw",
        "O3nfPV-k0-Vwju7Co4Mb-A",
        "r-tyOG9lUCelAntmf3_4hw",
        "941i1H69buwxuNYq2Ke0MQ",
        "Bs47CAFy7Gpts81BJ3bHmQ",
        "UEFOu7S6mfehb7f-VniI2A",
        "pDwNdwNsfIfhA-QrFjHMfA",
        "Bw8TGXPLb2MQcKpvdPwQWA",
        "GPH8zAvl8UGOVd1Nxk7QYQ",
        "Fi6qy3qG99E7tRilv6Eimg",
        "fA7k4lSVtL8ihnEPddHRjg",
        "DUh0subpBbInDxBuz3PdxA",
        "UguipXsMZE_AGDC0SkIwjg",
        "Fm-4Hxj1RDwhbroB6MaRow",
        "ddYokbH_fS-GWQNox-cjVw",
        "D6Nz-WDtgbDERN8G4ztITA",
        "nx2hCLMTdciyuZG2QWbDHw",
        "0S-2DM3KM6RgTgZVckfsMg",
        "dHUuKtsAXK7dAVAKTg-7lg",
        "4iYHhkp_KQex3t93IKNaOw",
        "dpVRBsdEkLPvqsSa7UMKUA",
        "i-5K6IXnnlh823Oyax8T2w",
        "aTbH3Nf4j7J9OOASUT8Nmg",
        "bFlM7NoKIzkUhUMjXJY2Cw",
        "ANB-ANo1yofdY3iTiZ6arA",
        "MZCECte7nZoQOvdkZOUzSg",
        "M-cafYN1lQvS-u11jwNt4g",
        "x518c9KYWp2I1vsAxTDX7g",
        "iBww2hzv5y0E_55ltMgTvQ",
        "iSwYUD4zyuOCfYHnSmE3TQ",
        "Ev7EW5zrzvBRyA9YE5GUZw",
        "8YvoSP_1H3ffc6dVVfRDlw",
        "7gQRVqlSGxhmPMqlvizTHg",
        "lZHB-w1JHuj0xoRm2vi8aw",
        "yW3hRiZmwJH79OBzXoGkZg",
        "ICpq-CdqW_j5xAIyKTZ1eQ",
        "NjZz_dHSAuL1vGpa7QFrzQ",
        "AeU_LgnsbcoXWdoj9ZWudw",
        "KB3bUtn44Y_WQLen3edVPw",
        "M8l6bI-X0sqalfTdcErRlQ",
        "0dGKjuJYhXLOSARR_x27ZQ",
        "pu-MSSI3W_z_9pwgGB_P-Q",
        "6_YmivPyJDjN2jTETAIhyw",
        "OfMF6Pl-WLOTkOo-DgwJXg",
        "9JO_8NKLBnUiJaETnvafDQ",
        "mbAvySgY1rgYdh9Vnngtvw",
        "qGZ4oWwi6TiA39ziikpllg",
        "lF08ZjsRunPoPhSREbR62g",
        "iYZ5fPI6R_XY93ydN84NxQ",
        "gL39ozhyzEx4moE8A6C-mg",
        "Bq4dm_5nLjda_1fAldjWWQ",
        "sdoxJqSGVe0U-mXSEMlc1w",
        "hIAM8Bt7VUuRYKIQbArvAw",
        "32sLM9sb190M63czy8tFxA",
        "ELIu5xOaZy4DDWlodHFcGg",
        "I-OoipDvz6MEEJPBjVozdg",
        "ktgPH_A7NkDrcmmyctj2iA",
        "XiQHEBVwTWyyhPSmOU-nYA"
    ]
    pid_list = ["0zd3t7k9CYcwTLevh0KFHw",
        "Fi6qy3qG99E7tRilv6Eimg",
        "8YvoSP_1H3ffc6dVVfRDlw"]
    pid_list = ["C75Haa47Oeq5DsPwA0BMSw", "t27RQEsrYJzjxEJr4PWgMA"]
    wx_crawler = WeChatArticleCrawler(blog_root="../source", download_images=True)
    wx_crawler.crawl_batch(pid_list)
