import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// ============================================================================
// PART 1: 原有的 SeedHub 节点逻辑 (完整保留)
// ============================================================================

let t = {
    "auto": "🚀 Auto",
    "manual": "🎲 Random",
    "last": "♻️ Last",
    "no_history": "No history found"
};

const formatSeed = (seed) => {
    if (!seed) return "";
    const str = String(seed);
    if (str.length <= 12) return str;
    return str.slice(0, 4) + "..." + str.slice(-4);
};

app.registerExtension({
    name: "Supernova.SeedHub",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name === "SeedHub") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                onNodeCreated?.apply(this, arguments);

                const self = this;
                const seedWidget = this.widgets.find(w => w.name === "seed");

                const ctrlWidget = this.widgets.find(w => w.name === "control_after_generate");
                if (ctrlWidget) this.widgets.splice(this.widgets.indexOf(ctrlWidget), 1);

                this.addWidget("button", t.auto, "", () => {
                    seedWidget.value = -1;
                });

                this.addWidget("button", t.manual, "", () => {
                    seedWidget.value = Math.floor(Math.random() * 1125899906842624);
                });

                this.lastSeed = null;

                const lastBtn = this.addWidget("button", t.last, "", () => {
                    let targetSeed = self.lastSeed;
                    if (!targetSeed) {
                        const history = app.nodeOutputs?.[self.id];
                        if (history && history.seed) {
                            targetSeed = Array.isArray(history.seed) ? history.seed[0] : history.seed;
                        }
                    }

                    if (targetSeed) {
                        seedWidget.value = targetSeed;
                    } else {
                        alert(t.no_history);
                    }
                });

                const executionHandler = (e) => {
                    if (e.detail.node === String(self.id)) {
                        const output = e.detail.output;
                        if (output && output.seed) {
                            const realSeed = Array.isArray(output.seed) ? output.seed[0] : output.seed;
                            self.lastSeed = realSeed;
                            lastBtn.name = `${t.last}: ${formatSeed(realSeed)}`;

                            const size = self.computeSize();
                            size[0] = Math.max(size[0], 220);
                            self.setSize(size);
                        }
                    }
                };

                app.api.addEventListener("executed", executionHandler);

                this.onRemoved = function () {
                    app.api.removeEventListener("executed", executionHandler);
                };

                this.setSize([220, 160]);
            };
        }
    }
});


// ============================================================================
// PART 2: ComfyUI 原生设置项 (Settings) 与全局/保存提示音
// ============================================================================

// 1. 设置项常量与默认值
const SETTING_IDS = {
    // 基础暂停/提示音
    SOUND_ENABLED: "🪐Superova.Sound.Enabled",
    SOUND_VOLUME: "🪐Superova.Sound.Volume",
    SOUND_CUSTOM_URL: "🪐Superova.Sound.CustomUrl",

    // 【新增】保存图片专属提示音设置
    SAVE_SOUND_ENABLED: "🪐Superova.SaveSound.Enabled",
    SAVE_SOUND_VOLUME: "🪐Superova.SaveSound.Volume",
    SAVE_SOUND_URL: "🪐Superova.SaveSound.Url",

    // 其他
    MOUSE_FOLLOW_DEFAULT: "🪐Superova.Compare.DefaultMouseFollow"
};

const DEFAULT_SETTINGS = {
    [SETTING_IDS.SOUND_ENABLED]: true,
    [SETTING_IDS.SOUND_VOLUME]: 0.5,
    [SETTING_IDS.SOUND_CUSTOM_URL]: "../audio/sound.mp3",

    [SETTING_IDS.SAVE_SOUND_ENABLED]: true,
    [SETTING_IDS.SAVE_SOUND_VOLUME]: 0.8,
    [SETTING_IDS.SAVE_SOUND_URL]: "../audio/sound.mp3",

    [SETTING_IDS.MOUSE_FOLLOW_DEFAULT]: false
};

// 2. 音频播放辅助方法
function playAudioFile(url, volume) {
    try {
        const audio = new Audio(url);
        audio.volume = Math.max(0, Math.min(1, isNaN(volume) ? 0.5 : volume));
        audio.play().catch(e => console.debug("[Supernova] Audio play prevented:", e));
    } catch (e) {
        console.error("[Supernova] Audio error:", e);
    }
}

/**
 * 播放通用节点就绪/暂停提示音（供其他 JS 调用）
 */
export function playSupernovaSound(overrideVolume = null) {
    const isEnabled = app.ui.settings.getSettingValue(
        SETTING_IDS.SOUND_ENABLED,
        DEFAULT_SETTINGS[SETTING_IDS.SOUND_ENABLED]
    );
    if (!isEnabled) return;

    const url = app.ui.settings.getSettingValue(SETTING_IDS.SOUND_CUSTOM_URL, DEFAULT_SETTINGS[SETTING_IDS.SOUND_CUSTOM_URL]);
    const vol = overrideVolume !== null ? overrideVolume : app.ui.settings.getSettingValue(SETTING_IDS.SOUND_VOLUME, DEFAULT_SETTINGS[SETTING_IDS.SOUND_VOLUME]);
    playAudioFile(url, parseFloat(vol));
}
// 挂载到全局
window.playSupernovaSound = playSupernovaSound;

window.playSupernovaCustomSound = function (url) {
    if (!url || url.trim() === "") return;
    const vol = app.ui.settings.getSettingValue(SETTING_IDS.SOUND_VOLUME, DEFAULT_SETTINGS[SETTING_IDS.SOUND_VOLUME]);
    
    let finalUrl = url;
    
    // 如果是网络链接(http)或base64(data:)或已经是绝对路由(/)，则直接播放。
    // 否则，说明它是本地路径(如 C:\1.mp3) 或 相对文件名(如 1.mp3)，需要交由 Python 后端代理读取。
    if (!url.startsWith("http://") && !url.startsWith("https://") && !url.startsWith("data:") && !url.startsWith("/")) {
        // encodeURIComponent 防止路径中的空格或中文字符导致请求断掉，加时间戳防止浏览器缓存更换前的音频
        finalUrl = `/supernova/audio_stream?path=${encodeURIComponent(url)}&t=${Date.now()}`;
    }
    
    playAudioFile(finalUrl, parseFloat(vol));
};

/**
 * 播放保存图片成功提示音（由设置面板完全控制）
 */
function playSaveImageSound() {
    const isEnabled = app.ui.settings.getSettingValue(
        SETTING_IDS.SAVE_SOUND_ENABLED,
        DEFAULT_SETTINGS[SETTING_IDS.SAVE_SOUND_ENABLED]
    );
    if (!isEnabled) return;

    const url = app.ui.settings.getSettingValue(SETTING_IDS.SAVE_SOUND_URL, DEFAULT_SETTINGS[SETTING_IDS.SAVE_SOUND_URL]);
    const vol = app.ui.settings.getSettingValue(SETTING_IDS.SAVE_SOUND_VOLUME, DEFAULT_SETTINGS[SETTING_IDS.SAVE_SOUND_VOLUME]);
    playAudioFile(url, parseFloat(vol));
}

export function getDefaultMouseFollow() {
    return app.ui.settings.getSettingValue(
        SETTING_IDS.MOUSE_FOLLOW_DEFAULT,
        DEFAULT_SETTINGS[SETTING_IDS.MOUSE_FOLLOW_DEFAULT]
    );
}

// 3. 注册设置面板与事件监听
app.registerExtension({
    name: "Supernova.Settings",
    init() {
        // --- 通用提示音设置 ---
        app.ui.settings.addSetting({
            id: SETTING_IDS.SOUND_ENABLED,
            name: "启用常规提示音 (Enable Notification Sound)",
            type: "boolean",
            defaultValue: DEFAULT_SETTINGS[SETTING_IDS.SOUND_ENABLED]
        });

        app.ui.settings.addSetting({
            id: SETTING_IDS.SOUND_VOLUME,
            name: "常规提示声音量 (Notification Sound Volume)",
            type: "slider",
            attrs: { min: 0, max: 1, step: 0.05 },
            defaultValue: DEFAULT_SETTINGS[SETTING_IDS.SOUND_VOLUME]
        });

        app.ui.settings.addSetting({
            id: SETTING_IDS.SOUND_CUSTOM_URL,
            name: "常规提示音文件路径 (Notification Sound URL)",
            type: "text",
            defaultValue: DEFAULT_SETTINGS[SETTING_IDS.SOUND_CUSTOM_URL]
        });

        // --- SaveImageWithSound 专用声音设置 ---
        app.ui.settings.addSetting({
            id: SETTING_IDS.SAVE_SOUND_ENABLED,
            name: "保存图片成功提示音开关 (Save Image Sound)",
            type: "boolean",
            defaultValue: DEFAULT_SETTINGS[SETTING_IDS.SAVE_SOUND_ENABLED]
        });

        app.ui.settings.addSetting({
            id: SETTING_IDS.SAVE_SOUND_VOLUME,
            name: "保存图片提示声音量 (Save Image Sound Volume)",
            type: "slider",
            attrs: { min: 0, max: 1, step: 0.05 },
            defaultValue: DEFAULT_SETTINGS[SETTING_IDS.SAVE_SOUND_VOLUME]
        });

        app.ui.settings.addSetting({
            id: SETTING_IDS.SAVE_SOUND_URL,
            name: "保存图片提示音文件路径 (Save Image Sound URL)",
            type: "text",
            defaultValue: DEFAULT_SETTINGS[SETTING_IDS.SAVE_SOUND_URL]
        });

        // --- 其它设置 ---
        app.ui.settings.addSetting({
            id: SETTING_IDS.MOUSE_FOLLOW_DEFAULT,
            name: "对比节点默认鼠标跟随 (Default Mouse Follow)",
            type: "boolean",
            defaultValue: DEFAULT_SETTINGS[SETTING_IDS.MOUSE_FOLLOW_DEFAULT]
        });
    },

    setup() {
        // 监听来自 Python 后端 SaveImageWithSound 的保存完成信号
        api.addEventListener("supernova_save_image_done", () => {
            playSaveImageSound();
        });
        // 监听经过声音节点的事件
        api.addEventListener("supernova_play_sound_node", (e) => {
            const data = e.detail;
            if (data.use_custom_path && data.audio_path) {
                window.playSupernovaCustomSound?.(data.audio_path);
            } else {
                // False 或 没有自定义路径时，播放默认音效
                window.playSupernovaSound?.();
            }
        });
    }
});