#!/usr/bin/env python3
"""
RSS 每日摘要生成器
支持去重功能
"""

import os
import sys
import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
import feedparser
import html

# 配置
OPML_FILE = "opml/feeds.opml"
DB_FILE = ".rss/articles.db"
OUTPUT_DIR = "Daily RSS"

# 创建目录
Path(DB_FILE).parent.mkdir(exist_ok=True)
Path(OUTPUT_DIR).mkdir(exist_ok=True)

# 数据库管理
class ArticleDB:
    def __init__(self, db_file):
        self.db_file = Path(db_file)
        self.seen = set()
        self._load()

    def _load(self):
        if self.db_file.exists():
            with open(self.db_file, 'r') as f:
                self.seen = set(line.strip() for line in f if line.strip())

    def is_seen(self, url):
        return self.hash_url(url) in self.seen

    def add(self, url):
        url_hash = self.hash_url(url)
        self.seen.add(url_hash)
        self._save()

    def hash_url(self, url):
        return hashlib.md5(url.encode()).hexdigest()

    def _save(self):
        with open(self.db_file, 'w') as f:
            for item in self.seen:
                f.write(f"{item}
")

    def count(self):
        return len(self.seen)

# 解析 OPML
def parse_opml(opml_file):
    """解析 OPML 文件，返回 RSS 源列表"""
    try:
        tree = ET.parse(opml_file)
        root = tree.getroot()
        
        sources = []
        
        # 尝试不同的命名空间
        namespaces = {
            'opml': 'http://www.opml.org/spec2',
            '': ''
        }
        
        # 查找所有 outline 元素
        for ns in namespaces.values():
            if ns:
                outlines = root.findall(f".//{ns}outline")
            else:
                outlines = root.findall(".//outline")
            
            if outlines:
                for outline in outlines:
                    # 只处理有 xmlUrl 属性的 outline（RSS 源）
                    xml_url = outline.get('xmlUrl', '')
                    if xml_url:
                        name = outline.get('text', outline.get('title', 'Unknown'))
                        sources.append({'name': name, 'url': xml_url})
        
        return sources
    except Exception as e:
        print(f"解析 OPML 失败: {e}", file=sys.stderr)
        return []

# 获取 RSS 内容
def fetch_rss(sources, db):
    """获取所有 RSS 源的新文章"""
    all_articles = []
    total_new = 0
    total_seen = 0

    for source in sources:
        try:
            feed = feedparser.parse(source['url'])

            for entry in feed.entries[:3]:  # 每个源取3篇
                link = entry.get('link', '')
                if not link:
                    continue

                if db.is_seen(link):
                    total_seen += 1
                    continue

                # 新文章
                db.add(link)
                total_new += 1

                article = {
                    'blog': source['name'],
                    'title': entry.get('title', '无标题'),
                    'link': link,
                    'description': entry.get('description', '')[:200],
                    'published': entry.get('published', '')
                }
                all_articles.append(article)

        except Exception as e:
            print(f"Error fetching {source['name']}: {e}", file=sys.stderr)
            continue

    return all_articles, total_new, total_seen

# 生成 Markdown
def generate_markdown(articles, total_new, total_seen, db_count):
    """生成 Markdown 笔记"""
    date = datetime.now().strftime("%Y-%m-%d")
    time = datetime.now().strftime("%H:%M")
    filename = f"RSS摘要_{date}.md"
    filepath = Path(OUTPUT_DIR) / filename

    content = f"""# 📰 RSS 每日摘要 - {date}

> 生成时间: {date} {time}

## 📊 今日统计

- 🆕 新文章: {total_new}
- 📋 已跳过（重复）: {total_seen}
- 📚 数据库总文章: {db_count}

---

## 📡 今日更新

"""

    for article in articles:
        content += f"### 📌 {article['blog']}

"
        content += f"- **{article['title']}**
"

        if article['description']:
            # 清理 HTML 标签
            desc = article['description']
            desc = desc.replace('<', ' <').replace('>', '> ')
            content += f"  > {desc}...
"

        content += f"  > 🔗 [阅读原文]({article['link']})
"

        if article['published']:
            content += f"  > 📅 {article['published']}
"

        content += "
"

    content += f"""---

## 📊 统计信息

| 项目 | 数量 |
|------|------|
| 🆕 新文章 | {total_new} |
| 📋 已跳过（重复） | {total_seen} |
| 📚 数据库总文章 | {db_count} |

- 生成时间: {date} {time}
- 数据来源: [HN 2025 热门博客](https://gist.github.com/emschwartz/e6d2bf860ccc367fe37ff953ba6de66b)

## 🔖 标签

#DailyRSS #技术博客 #HackerNews #新文章 #{date}

---

*本笔记由 GitHub Actions 自动生成*
"""

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    return filepath

# 主函数
def main():
    print("开始获取 RSS 内容...")

    # 初始化数据库
    db = ArticleDB(DB_FILE)

    # 解析 OPML
    if not Path(OPML_FILE).exists():
        print(f"错误: OPML 文件不存在: {OPML_FILE}")
        sys.exit(1)

    sources = parse_opml(OPML_FILE)
    print(f"找到 {len(sources)} 个 RSS 源")

    if not sources:
        print("警告: 没有找到任何 RSS 源")
        # 仍然生成一个空笔记
        filepath = generate_markdown([], 0, 0, db.count())
        print(f"
✅ 完成! (空笔记)")
        print(f"  笔记文件: {filepath}")
        return

    # 获取新文章
    articles, total_new, total_seen = fetch_rss(sources, db)

    # 生成 Markdown
    filepath = generate_markdown(articles, total_new, total_seen, db.count())

    print(f"
✅ 完成!")
    print(f"  新文章: {total_new}")
    print(f"  已跳过: {total_seen}")
    print(f"  数据库总数: {db.count()}")
    print(f"  笔记文件: {filepath}")

if __name__ == "__main__":
    main()
