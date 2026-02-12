#!/bin/bash
#
# RSS 每日摘要同步脚本
# 每天早上 9:00 自动从 GitHub 拉取最新摘要并同步到 Obsidian vault
#

set -e  # 遇到错误立即退出

# ============================================================================
# 配置
# ============================================================================

REPO_DIR="/Users/mei/ObsidianVaults/Daily RSS"
OBSIDIAN_DIR="/Users/mei/ObsidianVaults/RSS 摘要"
LOG_FILE="${REPO_DIR}/.rss/sync.log"
MAX_RETRIES=3
RETRY_DELAY=60  # 秒

# ============================================================================
# 日志函数
# ============================================================================

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# ============================================================================
# Git 同步函数（强制同步，丢弃本地修改）
# ============================================================================

sync_from_github() {
    log "📥 从 GitHub 拉取最新更新..."

    # 使用 fetch + reset 确保能获取最新内容，即使本地有修改
    git fetch origin main >> "$LOG_FILE" 2>&1 || {
        log "❌ Git fetch 失败"
        return 1
    }

    # 检查远程是否有新提交
    LOCAL_COMMIT=$(git rev-parse HEAD)
    REMOTE_COMMIT=$(git rev-parse origin/main)

    if [ "$LOCAL_COMMIT" = "$REMOTE_COMMIT" ]; then
        log "✅ 已经是最新版本"
    else
        log "🔄 发现新版本，正在同步..."
        log "   本地: $LOCAL_COMMIT"
        log "   远程: $REMOTE_COMMIT"

        # 强制重置到远程版本（丢弃本地修改）
        git reset --hard origin/main >> "$LOG_FILE" 2>&1 || {
            log "❌ Git reset 失败"
            return 1
        }

        log "✅ 同步完成"
    fi

    return 0
}

# ============================================================================
# 主流程
# ============================================================================

log "========================================="
log "开始同步 RSS 摘要到 Obsidian"

# 进入仓库目录
cd "$REPO_DIR" || {
    log "❌ 无法进入仓库目录: $REPO_DIR"
    exit 1
}

# 带重试的同步
RETRY_COUNT=0
while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if sync_from_github; then
        break
    fi

    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ $RETRY_COUNT -lt $MAX_RETRIES ]; then
        log "⏳ 等待 ${RETRY_DELAY} 秒后重试 ($RETRY_COUNT/$MAX_RETRIES)..."
        sleep $RETRY_DELAY
    fi
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    log "❌ 同步失败，已达到最大重试次数"
    exit 1
fi

# 获取今天的日期
TODAY=$(date '+%Y-%m-%d')
SOURCE_FILE="${REPO_DIR}/Daily RSS/RSS摘要_${TODAY}.md"
TARGET_FILE="${OBSIDIAN_DIR}/RSS摘要_${TODAY}.md"

# 检查 GitHub Actions 是否已运行
log "🔍 检查最新 commit..."
LATEST_COMMIT_MSG=$(git log -1 --pretty=format:"%s")
LATEST_COMMIT_DATE=$(git log -1 --pretty=format:"%ai" | cut -d' ' -f1)

log "   最新提交: $LATEST_COMMIT_MSG"
log "   提交日期: $LATEST_COMMIT_DATE"

# 检查源文件是否存在
if [ ! -f "$SOURCE_FILE" ]; then
    log "⚠️  今天的摘要文件不存在: $SOURCE_FILE"
    log "   GitHub Actions 可能还未运行或失败"
    log "   查看: https://github.com/zhienmei9-coder/rss-daily-summary/actions"
    exit 0
fi

# 创建目标目录（如果不存在）
mkdir -p "$OBSIDIAN_DIR" || {
    log "❌ 无法创建目标目录: $OBSIDIAN_DIR"
    exit 1
}

# 复制文件
log "📄 复制文件: RSS摘要_${TODAY}.md"
cp "$SOURCE_FILE" "$TARGET_FILE" || {
    log "❌ 复制文件失败"
    exit 1
}

# 显示文件信息
FILE_SIZE=$(wc -c < "$TARGET_FILE")
ARTICLE_COUNT=$(grep -c "^- \*\*" "$TARGET_FILE" || echo "0")

log "✅ 同步完成!"
log "   文件: RSS摘要_${TODAY}.md"
log "   大小: ${FILE_SIZE} 字节"
log "   文章数: ${ARTICLE_COUNT}"
log "========================================="

exit 0
