/* ==========================================================
   章节与关卡系统
   - 管理章节进度、场景切换、小怪波次
   - 剧情对话、战斗场景、Boss 战的衔接
   ========================================================== */

const ChapterMgr = {
  currentChapter: 1,
  currentSceneIndex: 0,
  currentScene: null,

  // 当前小怪战斗状态
  enemies: [],
  currentWave: 0,
  waveCleared: false,
  allWavesCleared: false,

  init() {
    // 从存档读取进度
    const progress = GameState.player.chapterProgress || {};
    this.currentChapter = progress.chapter || 1;
    this.currentSceneIndex = progress.sceneIndex || 0;
  },

  /**
   * 开始第一章（首次游玩）
   */
  startGame() {
    this.currentChapter = 1;
    this.currentSceneIndex = 0;
    this._saveProgress();
    this.enterCurrentScene();
  },

  /**
   * 进入当前场景
   */
  enterCurrentScene() {
    const chapter = CONFIG.chapters[this.currentChapter - 1];
    if (!chapter) return;

    const scene = chapter.scenes[this.currentSceneIndex];
    if (!scene) {
      // 章节完成 → 进入中枢
      this._onChapterComplete();
      return;
    }

    this.currentScene = scene;

    if (scene.type === 'story') {
      // 剧情场景
      StoryMgr.play(scene.dialogues || [], () => {
        this.nextScene();
      });
      SceneMgr.show('story');
    } else if (scene.type === 'battle') {
      // 小怪战斗场景
      this._startWaveBattle(scene);
    }
  },

  nextScene() {
    this.currentSceneIndex++;
    this._saveProgress();
    this.enterCurrentScene();
  },

  _saveProgress() {
    if (!GameState.player.chapterProgress) GameState.player.chapterProgress = {};
    GameState.player.chapterProgress.chapter = this.currentChapter;
    GameState.player.chapterProgress.sceneIndex = this.currentSceneIndex;
    GameState.save();
  },

  _onChapterComplete() {
    // 章节完成 → 去中枢大厅
    SceneMgr.show('hub');
    HubMgr.start();
  },

  // ---- 小怪战斗 ----

  _startWaveBattle(scene) {
    this.enemies = [];
    this.currentWave = 0;
    this.waveCleared = false;
    this.allWavesCleared = false;

    // 如果有战前对话
    if (scene.dialogueBefore && scene.dialogueBefore.length) {
      StoryMgr.play(scene.dialogueBefore, () => {
        this._enterBattleScene(scene);
      });
      SceneMgr.show('story');
    } else {
      this._enterBattleScene(scene);
    }
  },

  _enterBattleScene(scene) {
    // 切到战斗场景
    SceneMgr.show('battle');
    // 启动小怪战斗模式
    BattleSys.startWaveBattle(scene, () => {
      this._onWaveBattleComplete(scene);
    });
  },

  _onWaveBattleComplete(scene) {
    // 战斗胜利
    if (scene.dialogueAfter && scene.dialogueAfter.length) {
      StoryMgr.play(scene.dialogueAfter, () => {
        this.nextScene();
      });
      SceneMgr.show('story');
    } else {
      this.nextScene();
    }
  },

  /**
   * 是否已经完成了第一章（可以进入中枢）
   */
  isChapter1Complete() {
    const progress = GameState.player.chapterProgress;
    if (!progress) return false;
    if (progress.chapter > 1) return true;
    const chapter = CONFIG.chapters[0];
    return progress.sceneIndex >= (chapter ? chapter.scenes.length : 0);
  },
};
