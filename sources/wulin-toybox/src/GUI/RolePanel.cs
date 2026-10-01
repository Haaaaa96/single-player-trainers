// Modified in this research snapshot; see NOTICE.txt for scope.
using TMPro;
using WuLin;

namespace HaxxToyBox.GUI;

[RegisterInIl2Cpp]
internal class RolePanel : MonoBehaviour
{
    private ToggleGroup _roleList;
    private TMP_Text _status;
    
    public GameCharacterInstance Character = null;

    public GameObject LeftInfoGroup;
    public GameObject RightInfoGroup;
    public GameObject BottomInfoGroup;
    public GameObject AdditionInfoGroup;

    public Transform TraitList;
    public GameObject TraitEntryPrefab;

    readonly string[] leftRoleInfoKeys = {
        "gongji", "qinggong", "quanzhang", "shuadao", "duanbing", "mingzhong", "baoji", "yishu", "anqi", "wuxuechangshi"
    };

    readonly string[] rightRoleInfoKeys = {
        "fangyu", "jiqi", "yujian", "changbing", "yinlv", "shanbi", "gedang", "dushu", "hubo", "shizhannengli"
    };

    readonly string[] additionRoleInfoKeys = {
        "bili", "tizhi", "minjie", "wuxing", "fuyuan"
    };

    readonly string[] bottomRoleInfoKeys = {
        "rende", "yiqi", "lijie", "xinyong", "zhihui","yongqi"
    };

    readonly string[] percentageKeys = {
        "mingzhong", "baoji", "shanbi", "gedang", "hubo"
    };

    readonly Dictionary<string, string> keyToLabelMap = new() {
        {"gongji", "攻击"}, {"qinggong", "轻功"}, {"quanzhang", "拳掌"}, {"shuadao", "耍刀"},
        {"duanbing", "短兵"}, {"mingzhong", "命中"}, {"baoji", "暴击"}, {"yishu", "医术"},
        {"anqi", "暗器"}, {"wuxuechangshi", "武学常识"}, {"hp", "生命"}, {"mp", "内力"},
        {"point", "冲穴点数"}, {"exp", "经验"}, {"lv", "等级"}, {"fangyu", "防御"}, {"jiqi", "集气速度"},
        {"yujian", "御剑"}, {"changbing", "长兵"}, {"yinlv", "乐器"}, {"shanbi", "闪避"},
        {"gedang", "格挡"}, {"dushu", "毒术"}, {"hubo", "互搏"}, {"shizhannengli", "实战能力"},
        {"bili", "臂力"}, {"tizhi", "体质"}, {"minjie", "敏捷"}, {"wuxing", "悟性"},
        {"fuyuan", "福缘"}, {"rende", "仁德"}, {"yiqi", "义气"}, {"lijie", "礼节"},
        {"xinyong", "信用"}, {"zhihui", "智慧"}, {"yongqi", "勇气"}, {"replv", "名声级别"},
        {"repexp", "名声经验"}, {"coin", "金币"}
     };

    public static RolePanel Instance { get; private set; }

    public RolePanel(IntPtr ptr) : base(ptr) { }

    private void Awake()
    {
        Instance = this;
        _status = GetComponentsInChildren<TMP_Text>(true).FirstOrDefault(t => (t.text ?? "").StartsWith("人物属性"));

        _roleList = transform.Find("RoleList/ScrollView/Viewport/Content").GetComponent<ToggleGroup>();
        LeftInfoGroup = transform.Find("RoleInfo/LeftInfo").gameObject;
        RightInfoGroup = transform.Find("RoleInfo/RightInfo").gameObject;
        BottomInfoGroup = transform.Find("RoleInfo/BottomInfo").gameObject;
        AdditionInfoGroup = transform.Find("RoleInfo/AdditionInfo").gameObject;

        TraitList = transform.Find("Traits/Viewport/Content");
        TraitEntryPrefab = transform.Find("Traits/Viewport/EntryPrefab").gameObject;
        TraitEntryPrefab.AddComponent<TraitDelEntry>();
    }

    private void SetupRoleList()
    {
        Character = null;
        var numRole = PlayerTeamManager.HasInstance ? PlayerTeamManager.Instance.TeamSize : 0;
        
        for (int i = 0; i < _roleList.transform.childCount; i++) {
            var entry = _roleList.transform.GetChild(i);
            entry.gameObject.SetActive(i < numRole);
            if (i >= numRole) continue;

            var role = PlayerTeamManager.Instance.GetTeamMemberByIndex(i);
            if (role == null) { entry.gameObject.SetActive(false); continue; }
            if (Character == null) Character = role;

            entry.Find("Content/Avatar/Avatar").GetComponent<Image>().sprite = role.GetPortrait(GameCharacterInstance.PortraitType.Small);
            entry.Find("Content/NameText").GetComponent<TextMeshProUGUI>().text = role.FullName;

            var toggle = entry.GetComponent<Toggle>();
            toggle.onValueChanged.RemoveAllListeners();
            toggle.SetIsOnWithoutNotify(i == 0);
            toggle.onValueChanged.AddListener(delegate (bool isOn){
                if (isOn) {
                    UpdateRoleInfo(role);
                }
            });
        }
    }

    private void OnEnable()
    {
        SetupRoleList();

        UpdateRoleInfo();
        ToyBox.LogMessage($"RolePanel read ready: team={(PlayerTeamManager.HasInstance ? PlayerTeamManager.Instance.TeamSize : 0)}, character={Character?.FullName ?? "none"}");
    }

    public void UpdateRoleInfo(GameCharacterInstance charac = null)
    {
        if (charac != null)
            Character = charac;
        //ToyBox.LogMessage($"{character.FullName} Selected.");

        UpdateInfoGroup(LeftInfoGroup, leftRoleInfoKeys);
        UpdateInfoGroup(RightInfoGroup, rightRoleInfoKeys);
        UpdateInfoGroup(BottomInfoGroup, bottomRoleInfoKeys);
        UpdateInfoGroup(AdditionInfoGroup, additionRoleInfoKeys);

        UpdateTraitList();
    }

    private void UpdateInfoGroup(GameObject group, string[] keys)
    {
        int iterations = Mathf.Min(group.transform.childCount, keys.Length);
        var propSource = GameCharacterInstance.FinalPropSource.Origin;
        for (int i = 0; i < iterations; i++) {
            Transform child = group.transform.GetChild(i);
            var inputObj = child.GetComponentInChildren<TMP_InputField>();
            if (inputObj == null) continue;

            string formatstr = percentageKeys.Contains(keys[i]) ? "F3" : "";

            inputObj.onValueChanged.RemoveAllListeners();
            inputObj.onEndEdit.RemoveAllListeners();
            inputObj.onSubmit.RemoveAllListeners();
            inputObj.interactable = Character != null;
            if (Character == null) { inputObj.SetTextWithoutNotify("未读取"); continue; }
            string propKey = keyToLabelMap[keys[i]];
            string display = Character.GetFinalPropAsDecimal(propKey, propSource).ToString(formatstr);
            inputObj.SetTextWithoutNotify(display);
            var observed = Character;
            inputObj.onSubmit.AddListener(delegate (string input) {
                if (inputObj.wasCanceled || Character == null || Character.Pointer != observed.Pointer || input == display) return;
                bool ret = ChangeProperty(propKey, input);
                if (!ret) {
                    inputObj.SetTextWithoutNotify(display);
                    if (_status != null) _status.text = "输入无效 · 百分比 0–1，品性 -100–100，其余为非负整数";
                }
                else {
                    UpdateRoleInfo();
                    if (_status != null) _status.text = $"已提交：{propKey} = {input} · 显示基础值 · 回车提交";
                }
            });
        }
    }

    private bool ChangeProperty(string propKey, string input)
    {
        if (Character == null || 
            !Il2CppSystem.Decimal.TryParse(input, out Il2CppSystem.Decimal value)) {
            return false;
        }

        if (!decimal.TryParse(input, out var number) || number < -100 || number > 999999) return false;
        bool moral = bottomRoleInfoKeys.Any(key => keyToLabelMap[key] == propKey);
        bool ratio = percentageKeys.Any(key => keyToLabelMap[key] == propKey);
        if (moral && (number < -100 || number > 100 || decimal.Truncate(number) != number)) return false;
        if (!moral && number < 0) return false;
        if (ratio && number > 1) return false;
        if (!ratio && decimal.Truncate(number) != number) return false;
        if (!HasCurrentCharacter()) return false;

        if (!Character.m_originProps.ContainsKey(propKey))
            Character.m_originProps.Add(propKey, 0);

        var diff = value - Character.m_originProps[propKey];
        Character.ChangeOriginProp(propKey, diff);
        ToyBox.LogMessage($"Role property updated: {Character.FullName} / {propKey} = {value}");

        return true;
    }

    private void UpdateTraitList()
    {
        if (Character == null) return;

        var traits = Character.GetAllTrait();

        for (int i = 0; i < traits.Count; i++) {
            var trait = traits[i];
            GameObject entry;
            if (i >= TraitList.childCount) {
                entry = Instantiate(TraitEntryPrefab, TraitList);
            }
            else {
                entry = TraitList.GetChild(i).gameObject;
            }
            entry.SetActive(true);
            entry.GetComponent<TraitDelEntry>().SetTrait(trait);
        }

        for (int i = traits.Count; i < TraitList.childCount; i++) {
            TraitList.GetChild(i).gameObject.SetActive(false);
        }

    }

    public bool HasCurrentCharacter()
    {
        if (Character == null || !PlayerTeamManager.HasInstance) return false;
        for (int i = 0; i < PlayerTeamManager.Instance.TeamSize; i++)
            if (PlayerTeamManager.Instance.GetTeamMemberByIndex(i)?.Pointer == Character.Pointer) return true;
        return false;
    }
}
