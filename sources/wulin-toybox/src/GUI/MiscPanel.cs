// Modified in this research snapshot; see NOTICE.txt for scope.
using GameData;
using TMPro;
using WuLin;
using HaxxToyBox.Config;
using System.Globalization;

namespace HaxxToyBox.GUI;

[RegisterInIl2Cpp]
internal class MiscPanel : MonoBehaviour
{
    private const long MaxCoin = 999999999;
    private const string InputHint = "金钱 0–999999999 文；能力经验 1–1000 倍；两项均按回车提交";
    public static MiscPanel Instance { get; private set; }
    
    private Switch _timeFreezeSwitch;
    private Switch _recoverSwitch;
    private Switch _noCombatSwitch;
    private Switch _relationSwitch;
    private Switch _enableAchieveSwitch;
    private Switch _ultimateMartialSwitch;

    private Slider _walkSpeedSlider;
    private Slider _battleSpeedSlider;
    private TMP_InputField _expInput;
    private TMP_InputField _coinInput;
    private TMP_Text _coinLabel;
    private TMP_Text _expLabel;
    private TMP_Text _feedbackLabel;
    private TMP_Text _achievementStatus;
    private float _achievementConfirmUntil = -1f;
    private IntPtr _observedInventory;
    private IntPtr _observedPlayer;
    private long _observedCoin;
    private GameTimer _speedTimer;

    private InputKeyUGUI _toggleKeyUI;
    private InputKeyUGUI _speedUpKeyUI;
    private InputKeyUGUI _speedDownKeyUI;
    private InputKeyUGUI _recoverKeyUI;

    public int ExpMultiple { get; private set; } = 1;
    public int WalkSpeed { get; private set; } = 1;
    public int BattleSpeed { get; private set; } = 1;

    public bool TimeFreezed => _timeFreezeSwitch != null && _timeFreezeSwitch.IsToggled();
    public bool RecoverEnabled => _recoverSwitch != null && _recoverSwitch.IsToggled();
    public bool NoCombat => _noCombatSwitch != null && _noCombatSwitch.IsToggled();
    public bool RelationEnabled => _relationSwitch != null && _relationSwitch.IsToggled();
    public bool EnableAchieve => _enableAchieveSwitch != null && _enableAchieveSwitch.IsToggled();
    // The upstream switch has no corresponding patch or other consumer.
    public bool UltimateMartial => false;

    public MiscPanel(IntPtr ptr) : base(ptr) { }

    private void Awake()
    {
        Instance = this;

        _timeFreezeSwitch = transform.Find("Content/SwitchFunc/TimeFreeze/Switch").gameObject.AddComponent<Switch>();
        _recoverSwitch = transform.Find("Content/SwitchFunc/Recover/Switch").gameObject.AddComponent<Switch>();
        _noCombatSwitch = transform.Find("Content/SwitchFunc/NoCombat/Switch").gameObject.AddComponent<Switch>();
        _relationSwitch = transform.Find("Content/SwitchFunc/Friendship/Switch").gameObject.AddComponent<Switch>();
        _enableAchieveSwitch = transform.Find("Content/SwitchFunc/EnableAchievement/Switch").gameObject.AddComponent<Switch>();
        _ultimateMartialSwitch = transform.Find("Content/SwitchFunc/UltimateMartial/Switch").gameObject.AddComponent<Switch>();
        _ultimateMartialSwitch.GetComponent<Button>().interactable = false;
        var unsupportedLabel = FindRowLabel("Content/SwitchFunc/UltimateMartial");
        if (unsupportedLabel != null) {
            unsupportedLabel.text = "无限武学：由扩展模块处理";
            unsupportedLabel.fontSize = 32;
            unsupportedLabel.fontSizeMin = 28;
            unsupportedLabel.fontSizeMax = 32;
            unsupportedLabel.enableAutoSizing = true;
        }

        _expInput = transform.Find("Content/InputFunc/SkillExp/NumInput").GetComponent<TMP_InputField>();
        _expLabel = FindRowLabel("Content/InputFunc/SkillExp");
        PrepareInput(_expInput);
        _expInput.onSubmit.AddListener(SubmitExpMultiple);

        _coinInput = transform.Find("Content/InputFunc/Gold/NumInput").GetComponent<TMP_InputField>();
        _coinLabel = FindRowLabel("Content/InputFunc/Gold");
        PrepareInput(_coinInput);
        _coinInput.onSubmit.AddListener(SubmitCoin);
        SetLabel(_coinLabel, "金钱（文）");
        SetLabel(_expLabel, "能力经验倍率");
        _feedbackLabel = PrepareFeedbackHeader();

        var walkspeedSlider = transform.Find("Content/SliderFunc/WalkSpeed/Slider");
        walkspeedSlider.Find("Text").gameObject.AddComponent<SliderAmountText>();
        _walkSpeedSlider = walkspeedSlider.GetComponent<Slider>();
        PrepareSpeedSlider(_walkSpeedSlider);
        _walkSpeedSlider.onValueChanged.AddListener((float value) => {
            WalkSpeed = (int)_walkSpeedSlider.value;
        });

        _battleSpeedSlider = transform.Find("Content/SliderFunc/BattleSpeed/Slider").GetComponent<Slider>();
        _battleSpeedSlider.transform.Find("Text").gameObject.AddComponent<SliderAmountText>();
        PrepareSpeedSlider(_battleSpeedSlider);
        _battleSpeedSlider.onValueChanged.AddListener((float value) => SetBattleSpeed((int)value));
        var speedLabel = FindRowLabel("Content/SliderFunc/BattleSpeed");
        if (speedLabel != null) speedLabel.text = "游戏速度（1倍关闭）";

        var buttonAchievements = transform.Find("Content/ButtonFunc/Achievement").gameObject;
        buttonAchievements.AddComponent<FadeButtonWrapper>();
        _achievementStatus = CreateAchievementStatus(buttonAchievements);
        buttonAchievements.GetComponent<Button>().interactable = _achievementStatus != null;
        buttonAchievements.GetComponent<Button>().onClick.RemoveAllListeners();
        buttonAchievements.GetComponent<Button>().onClick.AddListener(ConfirmAllAchievements);

        var buttonRecover = transform.Find("Content/ButtonFunc/Recover").gameObject;
        buttonRecover.AddComponent<FadeButtonWrapper>();
        buttonRecover.GetComponent<Button>().onClick.AddListener(RecoverAll);

        _toggleKeyUI = transform.Find("Content/ConfigFunc/PanelToggle").gameObject.AddComponent<InputKeyUGUI>();
        _speedUpKeyUI = transform.Find("Content/ConfigFunc/SpeedupToggle").gameObject.AddComponent<InputKeyUGUI>();
        _speedDownKeyUI = transform.Find("Content/ConfigFunc/SpeeddownToggle").gameObject.AddComponent<InputKeyUGUI>();
        _recoverKeyUI = transform.Find("Content/ConfigFunc/Recover").gameObject.AddComponent<InputKeyUGUI>();

        BindInputKey(_toggleKeyUI, ConfigManager.Canvas_Toggle);
        BindInputKey(_speedUpKeyUI, ConfigManager.SpeedUp_Toggle);
        BindInputKey(_speedDownKeyUI, ConfigManager.SpeedDown_Toggle);
        BindInputKey(_recoverKeyUI, ConfigManager.Recover_Toggle);
    }

    private void BindInputKey(InputKeyUGUI obj, ConfigElement config)
    {
        obj.Key = config.Value;
        obj.AllowAbortWithCancelButton = true;
        obj.ActiveText = "请按键（Esc取消）";
        obj.OnChanged += (KeyCode key, KeyCode modifierKey) => config.Value = key;
    }

    private void OnEnable()
    {
        CancelAchievementConfirmation();
        ShowFeedback(InputHint);
        RefreshCoin();
        _expInput.SetTextWithoutNotify(ExpMultiple.ToString(CultureInfo.InvariantCulture));
        SyncSpeedSlider(_walkSpeedSlider, WalkSpeed);
        SyncSpeedSlider(_battleSpeedSlider, BattleSpeed);
    }

    private TMP_Text FindRowLabel(string path)
    {
        var row = transform.Find(path);
        if (row == null) return null;
        foreach (var label in row.GetComponentsInChildren<TMP_Text>(true)) {
            if (label.GetComponentInParent<TMP_InputField>() == null &&
                label.GetComponentInParent<Slider>() == null &&
                label.GetComponentInParent<Switch>() == null) return label;
        }
        return null;
    }

    private static void SetLabel(TMP_Text label, string text, bool error = false)
    {
        if (label == null) return;
        label.text = text;
        label.color = error ? new Color(1f, 0.45f, 0.38f) : Color.white;
    }

    private TMP_Text PrepareFeedbackHeader()
    {
        // Reuse the page heading so feedback cannot consume the narrow input labels.
        foreach (var label in GetComponentsInChildren<TMP_Text>(true)) {
            var text = label.text?.Trim();
            if (text != "辅助" && text != "Misc") continue;
            var rect = label.GetComponent<RectTransform>();
            if (rect == null) continue;
            var offsetMin = rect.offsetMin;
            var offsetMax = rect.offsetMax;
            rect.anchorMin = new Vector2(0, rect.anchorMin.y);
            rect.anchorMax = new Vector2(1, rect.anchorMax.y);
            rect.offsetMin = new Vector2(20, offsetMin.y);
            rect.offsetMax = new Vector2(-20, offsetMax.y);
            label.enableWordWrapping = false;
            label.enableAutoSizing = true;
            label.fontSize = 32;
            label.fontSizeMin = 28;
            label.fontSizeMax = 32;
            label.alignment = TextAlignmentOptions.Left;
            label.raycastTarget = false;
            return label;
        }
        ToyBox.LogWarning("Misc feedback heading was not found.");
        return null;
    }

    private void ShowFeedback(string message, bool error = false)
    {
        SetLabel(_feedbackLabel, "辅助 · " + message, error);
    }

    private static void PrepareInput(TMP_InputField input)
    {
        input.onValueChanged.RemoveAllListeners();
        input.onEndEdit.RemoveAllListeners();
        input.onSubmit.RemoveAllListeners();
        input.lineType = TMP_InputField.LineType.SingleLine;
        // Reject invalid complete values ourselves; never silently remove characters.
        input.characterValidation = TMP_InputField.CharacterValidation.None;
    }

    private void SubmitExpMultiple(string input)
    {
        if (!isActiveAndEnabled || _expInput.wasCanceled) return;
        if (!int.TryParse(input?.Trim(), NumberStyles.None, CultureInfo.InvariantCulture, out int value) ||
            value < 1 || value > 1000) {
            _expInput.SetTextWithoutNotify(ExpMultiple.ToString(CultureInfo.InvariantCulture));
            ShowFeedback("能力经验倍率须为1–1000的整数，本次未更改。", true);
            return;
        }
        ExpMultiple = value;
        _expInput.SetTextWithoutNotify(value.ToString(CultureInfo.InvariantCulture));
        ShowFeedback($"能力经验倍率已设为 {value} 倍；修改后按回车提交。");
    }

    private void RefreshCoin()
    {
        _observedInventory = IntPtr.Zero;
        _observedPlayer = IntPtr.Zero;
        var inventory = PlayerTeamManager.HasInstance && PlayerTeamManager.Instance.TeamSize > 0
            ? PlayerTeamManager.Instance.TeamInventory : null;
        _coinInput.interactable = inventory != null;
        if (inventory == null) {
            _coinInput.SetTextWithoutNotify("未读取");
            ShowFeedback("尚未读取金钱，请先进入存档。", true);
            return;
        }
        _observedInventory = inventory.Pointer;
        _observedPlayer = PlayerTeamManager.Instance.PlayerDataInstance?.Pointer ?? IntPtr.Zero;
        _observedCoin = inventory.GetCurrency(CurrencyType.Coin);
        _coinInput.SetTextWithoutNotify(_observedCoin.ToString(CultureInfo.InvariantCulture));
    }

    private void SubmitCoin(string input)
    {
        if (!isActiveAndEnabled || _coinInput.wasCanceled) return;
        if (!long.TryParse(input?.Trim(), NumberStyles.None, CultureInfo.InvariantCulture, out long value) || value > MaxCoin) {
            _coinInput.SetTextWithoutNotify(_observedCoin.ToString(CultureInfo.InvariantCulture));
            ShowFeedback("金钱须为0–999999999文的整数，本次未更改。", true);
            return;
        }
        var inventory = PlayerTeamManager.HasInstance && PlayerTeamManager.Instance.TeamSize > 0
            ? PlayerTeamManager.Instance.TeamInventory : null;
        if (inventory == null || _observedInventory == IntPtr.Zero || inventory.Pointer != _observedInventory ||
            _observedPlayer == IntPtr.Zero || PlayerTeamManager.Instance.PlayerDataInstance?.Pointer != _observedPlayer ||
            inventory.GetCurrency(CurrencyType.Coin) != _observedCoin) {
            RefreshCoin();
            ShowFeedback("金钱目标或余额已变化；已刷新，请重新输入并按回车。", true);
            return;
        }
        if (value == _observedCoin) {
            ShowFeedback($"金钱仍为 {value} 文，无需更改。");
            return;
        }
        try {
            inventory.SetCurrency(CurrencyType.Coin, value);
            RefreshCoin();
            ShowFeedback(_observedCoin == value ? $"金钱已设为 {_observedCoin} 文，并已读回确认。" : "金钱读回与输入不符，请检查实际余额。", _observedCoin != value);
        }
        catch (Exception ex) {
            _observedInventory = IntPtr.Zero;
            _coinInput.interactable = false;
            ShowFeedback("金钱提交异常，结果待核实；请重新打开本页。", true);
            ToyBox.LogWarning("Coin update result is unknown: " + ex.Message);
        }
    }

    private static void PrepareSpeedSlider(Slider slider)
    {
        slider.onValueChanged.RemoveAllListeners();
        slider.wholeNumbers = true;
        slider.minValue = 1;
        slider.maxValue = float.IsFinite(slider.maxValue) ? Math.Max(1, slider.maxValue) : 1;
        SyncSpeedSlider(slider, 1);
    }

    private static void SyncSpeedSlider(Slider slider, int value)
    {
        slider.SetValueWithoutNotify(value);
        var label = slider.transform.Find("Text")?.GetComponent<TMP_Text>();
        if (label != null) label.text = value.ToString(CultureInfo.InvariantCulture);
    }

    private void SetBattleSpeed(int value)
    {
        value = Mathf.Clamp(value, 1, (int)_battleSpeedSlider.maxValue);
        if (value == 1) {
            ReleaseSpeed();
            BattleSpeed = 1;
        }
        else if (PlayerTeamManager.HasInstance && PlayerTeamManager.Instance.TeamSize > 0 && GameTimer.HasInstance) {
            var timer = GameTimer.Instance;
            if (_speedTimer != null && _speedTimer.Pointer != timer.Pointer) ReleaseSpeed();
            _speedTimer = timer;
            _speedTimer.AddOrSetTimeScale(this, value);
            BattleSpeed = value;
        }
        SyncSpeedSlider(_battleSpeedSlider, BattleSpeed);
    }

    private void ReleaseSpeed()
    {
        // Release only this panel's speed owner; canvas/game pauses keep their owners.
        if (_speedTimer != null) _speedTimer.RemoveTimeScale(this);
        _speedTimer = null;
    }

    private TMP_Text CreateAchievementStatus(GameObject button)
    {
        GameObject labelObject = null;
        try {
            // Cloned prefab text components are not reliable with this interop build.
            var template = button.GetComponentInChildren<TMP_Text>(true);
            labelObject = new GameObject("AchievementWarning");
            labelObject.transform.SetParent(button.transform, false);
            var label = labelObject.AddComponent<TextMeshProUGUI>();
            if (label == null) throw new InvalidOperationException("Could not create achievement warning text.");
            try {
                if (template != null && template.font != null) label.font = template.font;
            }
            catch (Exception ex) {
                ToyBox.LogWarning("Achievement warning font fallback: " + ex.Message);
            }
            label.raycastTarget = false;
            label.richText = false;
            label.enableWordWrapping = true;
            label.enableAutoSizing = true;
            label.fontSize = 32;
            label.fontSizeMin = 28;
            label.fontSizeMax = 32;
            label.alignment = TextAlignmentOptions.Center;
            var rect = label.GetComponent<RectTransform>();
            rect.anchorMin = new Vector2(0, 1);
            rect.anchorMax = new Vector2(1, 1);
            rect.pivot = new Vector2(0.5f, 0);
            rect.anchoredPosition = new Vector2(0, 4);
            rect.sizeDelta = new Vector2(0, 64);
            return label;
        }
        catch (Exception ex) {
            if (labelObject != null) Destroy(labelObject);
            ToyBox.LogWarning("Achievement warning unavailable; unlock button disabled: " + ex.Message);
            return null;
        }
    }

    private void ConfirmAllAchievements()
    {
        if (!isActiveAndEnabled || _achievementStatus == null || !PlayerTeamManager.HasInstance || PlayerTeamManager.Instance.TeamSize == 0) return;
        if (_achievementConfirmUntil < 0 || Time.realtimeSinceStartup > _achievementConfirmUntil) {
            _achievementConfirmUntil = Time.realtimeSinceStartup + 10f;
            SetLabel(_achievementStatus, "10秒内再次点击确认", true);
            ShowFeedback("全部成就将永久解锁、无法撤销。10秒内再点按钮确认；离开本页取消。", true);
            return;
        }
        CancelAchievementConfirmation();
        // Preserve the upstream completion path; a second click authorizes this batch.
        var achievementDB = BaseDataClass.GetGameData<AchievementDataScriptObject>().data;
        foreach (var id in achievementDB.Keys) {
            MonoSingleton<AchievementManager>.Instance.Complate(id);
        }
    }

    private void CancelAchievementConfirmation()
    {
        if (_achievementConfirmUntil >= 0) ShowFeedback(InputHint);
        _achievementConfirmUntil = -1f;
        SetLabel(_achievementStatus, "永久解锁，无法撤销", true);
    }

    private void Update()
    {
        if (_achievementConfirmUntil >= 0 && Time.realtimeSinceStartup > _achievementConfirmUntil)
            CancelAchievementConfirmation();
    }

    private void OnDisable()
    {
        // Switching pages or closing the canvas cancels this irreversible action.
        CancelAchievementConfirmation();
    }

    private void OnDestroy()
    {
        ReleaseSpeed();
        if (Instance == this) Instance = null;
    }

    public static void RecoverAll()
    {
        if (!PlayerTeamManager.HasInstance || IsEditingInput()) return;
        var teamManager = PlayerTeamManager.Instance;
        if (teamManager == null) return;
        teamManager.ModifyProp("队伍体力", 100);
        teamManager.ModifyProp("队伍心情", 100);
        for (int i = 0; i < teamManager.TeamSize; i++) {
            teamManager.GetTeamMemberByIndex(i)?.FullyRecover();
        }
    }

    public static void SpeedDown()
    {
        if (Instance == null || IsEditingInput()) return;
        Instance.SetBattleSpeed(Instance.BattleSpeed - 1);
    }

    public static void SpeedUp()
    {
        if (Instance == null || IsEditingInput()) return;
        Instance.SetBattleSpeed(Instance.BattleSpeed + 1);
    }

    public static bool IsEditingInput()
    {
        if (InputKeyUGUI.CapturedThisFrame) return true;
        var selected = UnityEngine.EventSystems.EventSystem.current?.currentSelectedGameObject;
        if (selected != null && selected.GetComponentInParent<TMP_InputField>()?.isFocused == true) return true;
        return Instance != null &&
            ((Instance._toggleKeyUI != null && Instance._toggleKeyUI.IsActive) ||
             (Instance._speedUpKeyUI != null && Instance._speedUpKeyUI.IsActive) ||
             (Instance._speedDownKeyUI != null && Instance._speedDownKeyUI.IsActive) ||
             (Instance._recoverKeyUI != null && Instance._recoverKeyUI.IsActive));
    }

}
