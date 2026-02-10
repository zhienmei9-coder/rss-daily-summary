#!/usr/bin/env python3
# 配置 SSL 上下文以支持 Substack 等 RSS 源
import ssl
import urllib.request
ssl._create_default_https_context = ssl._create_unverified_context

import os
import sys
import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
import feedparser
import html

# 配置
OPML_FILE = "opml/feeds.opml"
DB_FILE = ".rss/articles.db"
OUTPUT_DIR = "Daily RSS"
ENABLE_TRANSLATION = True  # 启用翻译
MAX_ARTICLE_AGE_HOURS = 48  # 只抓取最近 48 小时内的文章

try:
    from deep_translator import GoogleTranslator
    translator = GoogleTranslator(source='auto', target='zh-CN')
    TRANSLATION_AVAILABLE = True
except ImportError:
    TRANSLATION_AVAILABLE = False
    print("Warning: Translation library not available, installing...")
    os.system("pip install deep-translator")

Path(DB_FILE).parent.mkdir(exist_ok=True)
Path(OUTPUT_DIR).mkdir(exist_ok=True)

class ArticleDB:
    def __init__(self, db_file):
        self.db_file = Path(db_file)
        self.seen = set()
        if self.db_file.exists():
            with open(self.db_file, 'r') as f:
                self.seen = set(line.strip() for line in f if line.strip())

    def is_seen(self, url):
        return hashlib.md5(url.encode()).hexdigest() in self.seen

    def add(self, url):
        self.seen.add(hashlib.md5(url.encode()).hexdigest())
        with open(self.db_file, 'w') as f:
            for item in self.seen:
                f.write(f"{item}\n")

    def count(self):
        return len(self.seen)

def translate_text(text, max_length=5000):
    """翻译文本到中文"""
    if not ENABLE_TRANSLATION or not text:
        return text

    # 检查是否已经包含中文
    if any('\u4e00' <= c <= '\u9fff' for c in text):
        return text

    # 清理 HTML 标签
    import re
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()

    if not text:
        return text

    # 限制长度
    if len(text) > max_length:
        text = text[:max_length] + "..."

    try:
        # 使用 deep_translator 翻译
        if TRANSLATION_AVAILABLE:
            from deep_translator import GoogleTranslator
            translator = GoogleTranslator(source='auto', target='zh-CN')
            translated = translator.translate(text)
            return translated
        else:
            return text + " [翻译功能暂不可用]"
    except Exception as e:
        print(f"Translation error: {e}", file=sys.stderr)
        return text

def parse_opml(opml_file):
    """解析 OPML 文件，返回 RSS 源列表 - 支持带命名空间和不带命名空间"""
    tree = ET.parse(opml_file)
    root = tree.getroot()

    sources = []
    # 首先尝试带命名空间的查找
    for outline in root.findall('.//{http://www.guyrutenberg.com/2008/opml}outline'):
        rss_url = outline.get('xmlUrl', '')
        blog_name = outline.get('text', outline.get('title', 'Unknown'))
        if rss_url:
            sources.append({'name': blog_name, 'url': rss_url})

    # 如果没找到，尝试不带命名空间的查找（标准 OPML 格式）
    if not sources:
        for outline in root.findall('.//outline'):
            rss_url = outline.get('xmlUrl', '')
            blog_name = outline.get('text', outline.get('title', 'Unknown'))
            if rss_url:
                sources.append({'name': blog_name, 'url': rss_url})

    return sources

def is_article_recent(published_date):
    """检查文章是否在指定的时间范围内"""
    if not published_date:
        # 如果没有发布日期，默认接受（可能是新文章）
        return True

    try:
        # 尝试解析多种日期格式
        parsed_date = feedparser._parse_date(published_date)
        if parsed_date:
            # 计算文章发布时间与当前时间的差值
            time_diff = datetime.now(parsed_date.tzinfo) - parsed_date
            # 检查是否在指定小时数内
            return time_diff.total_seconds() <= (MAX_ARTICLE_AGE_HOURS * 3600)
    except Exception as e:
        # 如果解析失败，默认接受
        print(f"Warning: Could not parse date '{published_date}': {e}", file=sys.stderr)

    return True

def main():
    db = ArticleDB(DB_FILE)

    if not Path(OPML_FILE).exists():
        print(f"Error: OPML file not found: {OPML_FILE}")
        sys.exit(1)

    sources = parse_opml(OPML_FILE)
    print(f"找到 {len(sources)} 个 RSS 源")

    articles = []
    total_new = 0
    total_seen = 0
    total_old = 0  # 统计因时间过滤而跳过的旧文章

    for source in sources:
        try:
            feed = feedparser.parse(source['url'])
            for entry in feed.entries[:3]:
                link = entry.get('link', '')
                if not link:
                    continue

                # 检查是否已见过
                if db.is_seen(link):
                    total_seen += 1
                    continue

                # 检查文章发布时间是否在允许范围内
                published = entry.get('published', entry.get('updated', ''))
                if not is_article_recent(published):
                    total_old += 1
                    # 将旧文章的 URL 也加入数据库，避免下次重复检查
                    db.add(link)
                    continue

                db.add(link)
                total_new += 1

                # 获取原始内容
                title = entry.get('title', 'No title')
                description = entry.get('description', '')

                # 翻译标题和描述
                if ENABLE_TRANSLATION:
                    print(f"翻译: {title[:50]}...")
                    title = translate_text(title)
                    description = translate_text(description[:300])

                article = {
                    'blog': source['name'],
                    'title': title,
                    'link': link,
                    'desc': description[:200],
                    'date': published
                }
                articles.append(article)
        except Exception as e:
            print(f"Error fetching {source['name']}: {e}", file=sys.stderr)

    # 生成 Markdown
    date_str = datetime.now().strftime("%Y-%m-%d")
    time_str = datetime.now().strftime("%H:%M")
    filepath = Path(OUTPUT_DIR) / f"RSS摘要_{date_str}.md"

    content = f"""# RSS 每日摘要 - {date_str}

> 生成时间: {date_str} {time_str}
> 🌐 已自动翻译为中文
> ⏰ 仅显示最近 {MAX_ARTICLE_AGE_HOURS} 小时内的文章

## 📊 今日统计

- 🆕 新文章: {total_new}
- 📋 已跳过（重复）: {total_seen}
- ⏰ 已跳过（过旧）: {total_old}
- 📚 数据库总文章: {db.count()}

---

## 📡 今日更新

"""

    for article in articles:
        content += f"### 📌 {article['blog']}\n\n"
        content += f"- **{article['title']}**\n"
        if article['desc'] and len(article['desc']) > 10:
            content += f"  > {article['desc']}...\n"
        content += f"  > 🔗 [阅读原文]({article['link']})\n"
        if article['date']:
            content += f"  > 📅 {article['date']}\n"
        content += "\n"

    content += f"""

---

## 📊 统计信息

| 项目 | 数量 |
|------|------|
| 🆕 新文章 | {total_new} |
| 📋 已跳过（重复） | {total_seen} |
| ⏰ 已跳过（过旧） | {total_old} |
| 📚 数据库总文章 | {db.count()} |

- 生成时间: {date_str} {time_str}
- 时间范围: 最近 {MAX_ARTICLE_AGE_HOURS} 小时
- 数据来源: [HN 2025 热门博客](https://gist.github.com/emschwartz/e6d2bf860ccc367fe37ff953ba6de66b)

## 🔖 标签

#DailyRSS #技术博客 #HackerNews #新文章 #{date_str} #中文翻译

---

*本笔记由 GitHub Actions 自动生成，内容已翻译为中文*
"""

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"\n✅ 完成!")
    print(f"  新文章: {total_new}")
    print(f"  已跳过（重复）: {total_seen}")
    print(f"  已跳过（过旧）: {total_old}")
    print(f"  数据库总数: {db.count()}")
    print(f"  笔记文件: {filepath}")

if __name__ == "__main__":
    main()
