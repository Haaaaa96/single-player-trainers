// Modified in this research snapshot; see NOTICE.txt for scope.
using TMPro;
using WuLin;
using System.IO;
using System.Text;
using GameData;
using Il2CppInterop.Runtime.Attributes;

namespace HaxxToyBox.GUI;

public enum MartialType
{
    Internal,
    Fist,
    Sword,
    Blade,
    LongWeapon,
    ShortWeapon,
    Music,
    Other
}

[RegisterInIl2Cpp]
internal class MartialPanel : MonoBehaviour
{
    private ToggleGroup _roleList;
    private ToggleGroup _typeGroup;

    private InfinityScrollKungfuData _infinityScroll;

    private MartialType _type;
    private Dictionary<MartialType, List<KungfuData>> _classifiedKungfus = new ();
    private readonly List<KungfuData> _emptyKungfus = new ();
    // A page/widget lifecycle is not a new game session. Keep uncertain writes
    // across closing/reopening the UI; only a positive readback clears its key.
    private static readonly HashSet<(IntPtr Character, int KungfuUid)> _unconfirmedLearning = new ();

    public GameCharacterInstance Character { get; private set; }

    public MartialPanel(IntPtr ptr) : base(ptr) { }
    public static MartialPanel Instance { get; private set; }

    private void Awake()
    {
        Instance = this;

        _roleList = transform.Find("RoleList/ScrollView/Viewport/Content").GetComponent<ToggleGroup>();
        _typeGroup = transform.Find("MartialList/TypeGroup").GetComponent<ToggleGroup>();

        for (int i = 0; i < _typeGroup.transform.childCount; i++) {
            var toggle = _typeGroup.transform.GetChild(i).GetComponent<Toggle>();
            var type = (MartialType)i;
            toggle.onValueChanged.RemoveAllListeners();
            toggle.onValueChanged.AddListener((bool value) => {
                if (value) {
                    UpdateMartialList(type);
                }
            });
        }

        var scrollView = transform.Find("MartialList/ScrollView").gameObject;
        var entryPrefab = transform.Find("MartialList/ScrollView/Viewport/EntryPrefab").gameObject;
        entryPrefab.AddComponent<MartialEntry>();
        _infinityScroll = scrollView.AddComponent<InfinityScrollKungfuData>();
        _infinityScroll.ItemPrefab = entryPrefab;
        _infinityScroll.Columns = 2;
        _infinityScroll.SpaceX = 10;
        _infinityScroll.SpaceY = 10;

        LoadMartialData();
    }

    private void OnEnable()
    {
        SetupRoleList();

        for (int i = 0; i < _typeGroup.transform.childCount; i++) {
            var toggle = _typeGroup.transform.GetChild(i).GetComponent<Toggle>();
            if (toggle != null) toggle.SetIsOnWithoutNotify(i == (int)MartialType.Internal);
        }
        UpdateMartialList(MartialType.Internal);
        ToyBox.LogMessage($"MartialPanel read ready: character={Character?.FullName ?? "none"}, category={_type}");
    }

    private void OnDisable()
    {
        Character = null;
    }

    private void LoadMartialData()
    {
        _classifiedKungfus.Clear();
        var kungfus = GameConfig.Instance.KungfuDataScriptObject.KungfuData;
        
        foreach(KungfuData kungfu in kungfus) {
            if (kungfu == null) continue;
            var type = GetMartialType(kungfu);
            if (!_classifiedKungfus.TryGetValue(type, out var kungfuList)) {
                kungfuList = new List<KungfuData>();
                _classifiedKungfus[type] = kungfuList;
            }
            kungfuList.InsertInOrder(kungfu, (a, b) => b.Rarity.CompareTo(a.Rarity));
        }
    }

    private void SetupRoleList()
    {
        Character = null;
        var numRole = PlayerTeamManager.HasInstance ? PlayerTeamManager.Instance.TeamSize : 0;

        // Clear inactive slots too: they may still refer to a previous party.
        for (int i = 0; i < _roleList.transform.childCount; i++) {
            var toggle = _roleList.transform.GetChild(i).GetComponent<Toggle>();
            toggle.onValueChanged.RemoveAllListeners();
            toggle.SetIsOnWithoutNotify(false);
        }

        for (int i = 0; i < _roleList.transform.childCount; i++) {
            var entry = _roleList.transform.GetChild(i);
            entry.gameObject.SetActive(i < numRole);
            if (i >= numRole) continue;

            var role = PlayerTeamManager.Instance.GetTeamMemberByIndex(i);
            if (role == null) { entry.gameObject.SetActive(false); continue; }

            entry.Find("Content/Avatar/Avatar").GetComponent<Image>().sprite = role.GetPortrait(GameCharacterInstance.PortraitType.Small);
            entry.Find("Content/NameText").GetComponent<TextMeshProUGUI>().text = role.FullName;

            var toggle = entry.GetComponent<Toggle>();
            if (Character == null) {
                Character = role;
                toggle.SetIsOnWithoutNotify(true);
            }
            toggle.onValueChanged.AddListener(delegate (bool isOn) {
                if (isOn) {
                    Character = IsCurrentTeamMember(role) ? role : null;
                    RefreshEntries();
                }
            });
        }
    }

    public static bool IsCurrentTeamMember(GameCharacterInstance character)
    {
        if (character == null || !PlayerTeamManager.HasInstance) return false;
        var team = PlayerTeamManager.Instance;
        for (int i = 0; i < team.TeamSize; i++) {
            var member = team.GetTeamMemberByIndex(i);
            if (member != null && member.Pointer == character.Pointer) return true;
        }
        return false;
    }

    public void RefreshEntries()
    {
        if (_infinityScroll != null) _infinityScroll.RefreshVisibleItems();
    }

    [HideFromIl2Cpp]
    public static bool IsLearningUnconfirmed(IntPtr character, int kungfuUid)
    {
        return _unconfirmedLearning.Contains((character, kungfuUid));
    }

    [HideFromIl2Cpp]
    public static void MarkLearningUnconfirmed(IntPtr character, int kungfuUid)
    {
        _unconfirmedLearning.Add((character, kungfuUid));
    }

    [HideFromIl2Cpp]
    public static void ConfirmLearningReadback(IntPtr character, int kungfuUid)
    {
        _unconfirmedLearning.Remove((character, kungfuUid));
    }

    [HideFromIl2Cpp]
    private void UpdateMartialList(MartialType type)
    {
        _type = type;
        
        _infinityScroll.Data = _classifiedKungfus.TryGetValue(type, out var kungfus) ? kungfus : _emptyKungfus;
    }

    [HideFromIl2Cpp]
    public static MartialType GetMartialType(KungfuData kungfu)
    {
        if (kungfu.KungfuType == KungfuType.Internal) {
            return MartialType.Internal;
        }

        if (kungfu.KungfuType != KungfuType.Outernal || kungfu.NeedWeaponToCast == null || kungfu.NeedWeaponToCast.Length == 0) {
            return MartialType.Other;
        }

        return kungfu.NeedWeaponToCast[0] switch {
            ItemType.Equip_Weapon_None => MartialType.Fist,
            ItemType.Equip_Weapon_Sword => MartialType.Sword,
            ItemType.Equip_Weapon_Blade => MartialType.Blade,
            ItemType.Equip_Weapon_Lance or ItemType.Equip_Weapon_Staff => MartialType.LongWeapon,
            ItemType.Equip_Weapon_Fan or ItemType.Equip_Weapon_Dagger or ItemType.Equip_Weapon_Brush => MartialType.ShortWeapon,
            ItemType.Equip_Weapon_Guqin or ItemType.Equip_Weapon_Flute or ItemType.Equip_Weapon_Pipa => MartialType.Music,
            _ => MartialType.Other,
        };
    }

    public static void WriteMartialToCSV(string outputPath)
    {
        var martials = GameConfig.Instance.KungfuDataScriptObject.KungfuData;

        StringBuilder csvContent = new StringBuilder();
        csvContent.AppendLine("Name,KungfuType,ItemType");

        foreach (var martial in martials) {
            string name = martial.UName;
            KungfuType kungfuType = martial.KungfuType;
            ItemType[] weaponTypes = martial.NeedWeaponToCast;

            string weaponTypeStr = string.Join(" ", weaponTypes); 

            csvContent.AppendLine($"{name},{kungfuType},{weaponTypeStr}");
        }

        File.WriteAllText(outputPath, csvContent.ToString(), Encoding.UTF8);
    }


}
