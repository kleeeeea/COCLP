#run /Users/l/klee_code/documents_common/funding/静安-训练数据管线/COCLP, create new conda env
# 用法:
#   bash run.sh            # = install + start
#   bash run.sh install    # 只建 conda env / clone ComfyUI / 装依赖 / 链接 custom_nodes
#   bash run.sh start      # 只在 tmux 里启动 ComfyUI (http://127.0.0.1:${PORT})
#   bash run.sh stop       # 关掉 tmux 里的 ComfyUI
# 可用环境变量覆盖: ENV_NAME, PYTHON_VERSION, COMFY_DIR, PORT, TMUX_SESSION
set -euo pipefail

COCLP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_NAME="${ENV_NAME:-coclp}"
PYTHON_VERSION="${PYTHON_VERSION:-3.11}"
# example/*.json 里的路径都是 ../example/..., 相对 ComfyUI 工作目录, 所以 ComfyUI 必须放在 COCLP/ComfyUI
# (已写进 COCLP/.git/info/exclude, 不会进 git)
COMFY_DIR="${COMFY_DIR:-$COCLP_DIR/ComfyUI}"
PORT="${PORT:-8188}"
TMUX_SESSION="${TMUX_SESSION:-coclp_comfyui}"
MINERU_REF="${MINERU_REF:-mineru-2.1.11-released}"
# ECNU_API_KEY 所在的 .env (同 git_repos/video_space/curl_latest-ecnu-plus.sh)
LLM_ENV_FILE="${LLM_ENV_FILE:-/Users/l/klee_code/git_repos/llm_evals/llm_common/llm_infer/.env}"

CONDA_BIN="${CONDA_BIN:-/Users/l/miniconda3/bin/conda}"
CONDA_ROOT="$("$CONDA_BIN" info --base)"
ENV_PYTHON="$CONDA_ROOT/envs/$ENV_NAME/bin/python"

# README 里要放进 ComfyUI/custom_nodes 的 4 个目录
CUSTOM_NODE_DIRS=(
    rgthree-comfy
    ComfyUI-to-Python-Extension
    Comfyui-LG_GroupExecutor
    Corpus_Cleansing_Pipeline
)

pip_install() {
    "$ENV_PYTHON" -m pip install --upgrade-strategy only-if-needed "$@"
}

step_create_env() {
    if [ -x "$ENV_PYTHON" ]; then
        echo "[env] conda env '$ENV_NAME' 已存在: $ENV_PYTHON"
    else
        echo "[env] 创建 conda env '$ENV_NAME' (python $PYTHON_VERSION)"
        "$CONDA_BIN" create --yes --name "$ENV_NAME" "python=$PYTHON_VERSION"
    fi
    pip_install --upgrade pip
    pip_install ipython
}

step_submodules() {
    echo "[git] 初始化子模块 (rgthree / to-Python / GroupExecutor / MinerU)"
    git -C "$COCLP_DIR" submodule update --init --recursive
    # 子模块锁的 MinerU 2.1.3 公式模型(UnimerMBart)在 transformers>=4.54 下报
    # "forward() got an unexpected keyword argument 'cache_position'", 上游 2.1.11 修了, 同一小版本线直接切过去
    local mineru_dir="$COCLP_DIR/Corpus_Cleansing_Pipeline/MinerU"
    git -C "$mineru_dir" rev-parse --quiet --verify "refs/tags/$MINERU_REF" >/dev/null || git -C "$mineru_dir" fetch --quiet origin tag "$MINERU_REF"
    git -C "$mineru_dir" checkout --quiet "$MINERU_REF"
    echo "[git] MinerU -> $MINERU_REF"
}

step_comfyui() {
    if [ -d "$COMFY_DIR/.git" ]; then
        echo "[comfy] ComfyUI 已存在: $COMFY_DIR"
    else
        echo "[comfy] clone ComfyUI -> $COMFY_DIR"
        git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git "$COMFY_DIR"
    fi
    local exclude_file="$(git -C "$COCLP_DIR" rev-parse --absolute-git-dir)/info/exclude"
    for pattern in /ComfyUI/ /install.log /example/test_out/; do
        grep --quiet --line-regexp --fixed-strings "$pattern" "$exclude_file" 2>/dev/null || echo "$pattern" >> "$exclude_file"
    done
    # torch 先装 (macOS 默认 wheel 自带 MPS; Linux 默认 wheel 带 CUDA)
    pip_install torch torchvision torchaudio
    pip_install --requirement "$COMFY_DIR/requirements.txt"
}

step_link_custom_nodes() {
    local custom_nodes="$COMFY_DIR/custom_nodes"
    mkdir -p "$custom_nodes"
    for name in "${CUSTOM_NODE_DIRS[@]}"; do
        local src="$COCLP_DIR/$name"
        local dst="$custom_nodes/$name"
        if [ -L "$dst" ] || [ ! -e "$dst" ]; then
            ln -sfn "$src" "$dst"
            echo "[link] $dst -> $src"
        else
            echo "[link] 跳过: $dst 已存在且不是软链接"
        fi
    done
}

step_python_deps() {
    echo "[deps] COCLP requirements"
    pip_install --requirement "$COCLP_DIR/Corpus_Cleansing_Pipeline/requirements.txt"
    # requirements.txt 里漏掉、但代码里 import 了的包
    pip_install pydub loguru regex openai pypdfium2 aiohttp
    echo "[deps] MinerU ($MINERU_REF, editable 安装, 和 Mineru_node.py 的 sys.path 一致)"
    pip_install --editable "$COCLP_DIR/Corpus_Cleansing_Pipeline/MinerU[core]"
    # MinerU 锁 transformers<5 -> huggingface-hub<1.0; 新版 datasets 要 hub>=1.x, 这里让 pip 回退到兼容的 datasets
    pip_install "huggingface-hub<1.0" "datasets" "transformers>=4.49,<5.0.0,!=4.51.0"
    # 各 ComfyUI 插件自带的 requirements
    for name in rgthree-comfy ComfyUI-to-Python-Extension Comfyui-LG_GroupExecutor; do
        local req="$COCLP_DIR/$name/requirements.txt"
        if [ -f "$req" ]; then
            echo "[deps] $req"
            pip_install --requirement "$req"
        fi
    done
}

step_check_import() {
    echo "[check] 导入 Corpus_Cleansing_Pipeline 节点"
    # train_label.py 会吞掉 ImportError, 所以先显式导入一遍关键库
    "$ENV_PYTHON" -c "import transformers, datasets, sklearn, torch, faster_whisper, markitdown, mineru; print('core libs OK, torch', torch.__version__)"
    (cd "$COMFY_DIR/custom_nodes" && "$ENV_PYTHON" -c "import Corpus_Cleansing_Pipeline as m; print(len(m.NODE_CLASS_MAPPINGS), 'nodes OK')")
}

do_install() {
    step_create_env
    step_submodules
    step_comfyui
    step_link_custom_nodes
    step_python_deps
    step_check_import
}

do_start() {
    if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
        echo "[start] tmux session '$TMUX_SESSION' 已在运行; 查看: tmux attach -t $TMUX_SESSION"
        return
    fi
    # 去隐私/分类/QA 等 LLM 节点的 api_key 控件填 None 时读 ECNU_API_KEY, 这里把 .env 导进 ComfyUI 进程
    local load_env=""
    if [ -f "$LLM_ENV_FILE" ]; then
        load_env="set -a; source '$LLM_ENV_FILE'; set +a;"
        echo "[start] 加载 LLM key: $LLM_ENV_FILE"
    fi
    tmux new-session -d -s "$TMUX_SESSION" -c "$COMFY_DIR" \
        "$load_env '$ENV_PYTHON' main.py --listen 127.0.0.1 --port $PORT 2>&1 | tee '$COMFY_DIR/comfyui.log'"
    echo "[start] ComfyUI 已在 tmux '$TMUX_SESSION' 中启动: http://127.0.0.1:$PORT"
    echo "        日志: $COMFY_DIR/comfyui.log ; 示例工作流: $COCLP_DIR/example/*.json"
}

do_stop() {
    tmux kill-session -t "$TMUX_SESSION" 2>/dev/null && echo "[stop] 已关闭 $TMUX_SESSION" || echo "[stop] 没有运行中的 $TMUX_SESSION"
}

case "${1:-all}" in
    install) do_install ;;
    start)   do_start ;;
    stop)    do_stop ;;
    all)     do_install; do_start ;;
    *)       echo "用法: bash run.sh [install|start|stop|all]"; exit 1 ;;
esac
