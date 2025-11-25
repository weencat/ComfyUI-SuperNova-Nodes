// 文件: MySoundNode/js/play_sound.js

import { api } from "../../../scripts/api.js";
import { app } from "../../../scripts/app.js";

app.registerExtension({
	name: "MySoundNode.PlaySound",
	setup() {
		api.addEventListener("play_sound_on_save", ({ detail }) => {
			console.log("(MySoundNode) 收到播放声音信号:", detail);
			
			const soundFile = detail.sound_file;
			const volume = detail.volume;

			if (!soundFile) {
				console.warn("(MySoundNode) 未指定声音文件。");
				return;
			}
			
			// 【核心修正】: 构建指向我们新 API 端点的 URL
			const url = `/audio/${encodeURIComponent(soundFile)}`;
			
			try {
				const audio = new Audio(url);
				audio.volume = parseFloat(volume);
				audio.play().catch(e => {
					console.error("(MySoundNode) 播放声音失败:", e);
				});
			} catch (e) {
				console.error("(MySoundNode) 创建 Audio 对象失败:", e);
			}
		});
	},
});