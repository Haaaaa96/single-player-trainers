// Modified in this research snapshot; see NOTICE.txt for scope.
using GameData;
using TMPro;
using WuLin;

namespace HaxxToyBox.GUI;

// Local changes (2026-09-30): global name/ID search, explicit first load and validated quantities.
// Original HaxxToyBox license is preserved in LICENSE.txt.

[RegisterInIl2Cpp]
public class ItemPanel : MonoBehaviour
{
    private TMP_InputField _numberInput;
    private TMP_InputField _searchInput;
    private TextMeshProUGUI _searchStatus;
    private TextMeshProUGUI _quantityStatus;
    private ToggleGroup _typeGroup;
    private ToggleGroup _subtypeGroup;

    private InfinityScrollItemData _infinityScroll;

    private ItemType[][] _typeList = { 
        new ItemType[] { ItemType.Equip,
            ItemType.Equip_Weapon, ItemType.Equip_Armor, ItemType.Equip_Amulet },
        new ItemType[] { ItemType.KungfuBook,
            ItemType.KungfuBook_Outer,
            ItemType.KungfuBook_Inner },
        new ItemType[] { ItemType.Consumeable_Recipe|ItemType.Consumeable_Edible,
            ItemType.Consumeable_Edible_Meal|ItemType.Consumeable_Edible_Fruit,
            ItemType.Consumeable_Edible_Elixir, ItemType.Consumeable_Edible_Medicine, ItemType.Consumeable_Recipe},
        new ItemType[] { ItemType.Consumeable_Material },
        new ItemType[] { ItemType.Misc_Map },
        new ItemType[] { ItemType.Misc^ItemType.Misc_Map },
    };
    private Dictionary<ItemType, List<ItemData>> _classifiedItems = new ();
    private readonly List<ItemData> _allItems = new ();
    private readonly Dictionary<int, string> _searchNames = new ();

    private int _selectedType = 0;
    private int _selectedSubtype;
    private string _query = string.Empty;
    private string _lastQuantityText;
    private bool _ready;

    public List<ItemData> ItemList = new ();
    public int Number { get; private set; } = 1;
    public bool IsQuantityValid { get; private set; } = true;

    public static ItemPanel Instance { get; private set; }

    public ItemPanel(IntPtr ptr) : base(ptr) { }

    private void Awake()
    {
        Instance = this;

        _typeGroup = transform.Find("TypeGroup/Toggles").GetComponent<ToggleGroup>();
        _subtypeGroup = transform.Find("SubtypeGroup").GetComponent<ToggleGroup>();
        for (int i = 0; i < _typeGroup.transform.childCount; i++) {
            var toggle = _typeGroup.transform.GetChild(i).GetComponent<Toggle>();
            toggle.onValueChanged.RemoveAllListeners();
            var type = i;
            toggle.onValueChanged.AddListener((bool value) => {
                if (value && _ready) {
                    _selectedType = type;
                    _selectedSubtype = 0;
                    UpdateSubToggles(type);
                    UpdateItemList(type);
                }
            });
        }

        for (int i = 0; i < _subtypeGroup.transform.childCount; i++) {
            var toggle = _subtypeGroup.transform.GetChild(i).GetComponent<Toggle>();
            int subtype = i;
            toggle.onValueChanged.RemoveAllListeners();
            toggle.onValueChanged.AddListener((bool value) => {
                if (value && _ready) {
                    UpdateItemList(_selectedType, subtype);
                }
            });
        }
        
        _numberInput = InputBinding.Find(transform.Find("NumInput"));
        _numberInput.contentType = TMP_InputField.ContentType.Standard;
        _numberInput.onValueChanged.RemoveAllListeners();
        _numberInput.onValueChanged.AddListener((string input) => {
            SyncInputChanges();
        });
        _numberInput.onEndEdit.RemoveAllListeners();
        _numberInput.onEndEdit.AddListener((string input) => {
            if (!_ready) return;
            SyncInputChanges();
            if (IsQuantityValid) {
                _lastQuantityText = Number.ToString();
                _numberInput.SetTextWithoutNotify(_lastQuantityText);
            }
        });
        _numberInput.SetTextWithoutNotify("1");
        _quantityStatus = CreateStatus(_numberInput, "QuantityStatus", 190);

        _searchInput = InputBinding.Find(transform.Find("SearchInput"));
        _searchStatus = CreateStatus(_searchInput, "SearchStatus", 0);
        var placeholder = _searchInput.placeholder?.GetComponent<TextMeshProUGUI>();
        if (placeholder != null) placeholder.text = "搜索全部物品名称 / ID";
        _searchInput.onValueChanged.RemoveAllListeners();
        _searchInput.onValueChanged.AddListener((string input) => {
            SyncInputChanges();
        });
        _query = SearchText.Normalize(_searchInput.text);

        var scrollView = transform.Find("ScrollView").gameObject;
        var entryPrefab = transform.Find("ScrollView/Viewport/EntryPrefab").gameObject;
        if (entryPrefab.GetComponent<ItemEntry>() == null) entryPrefab.AddComponent<ItemEntry>();
        _infinityScroll = scrollView.AddComponent<InfinityScrollItemData>();
        _infinityScroll.ItemPrefab = entryPrefab;
        _infinityScroll.Columns = 11;
        _infinityScroll.SpaceX = 25;
        _infinityScroll.SpaceY = 25;
        
        LoadItemData();
        _ready = true;
        for (int i = 0; i < _typeGroup.transform.childCount; i++) {
            _typeGroup.transform.GetChild(i).GetComponent<Toggle>().SetIsOnWithoutNotify(i == _selectedType);
        }
        UpdateSubToggles(_selectedType);
        ValidateQuantity(true);
        UpdateItemList(_selectedType);
    }

    private void SyncInputChanges()
    {
        if (!_ready) return;
        string query = SearchText.Normalize(_searchInput.text);
        if (!string.Equals(query, _query, StringComparison.Ordinal)) {
            _query = query;
            UpdateItemList(_selectedType, _selectedSubtype);
            string loggedQuery = query.Replace('\r', ' ').Replace('\n', ' ');
            if (loggedQuery.Length > 100) loggedQuery = loggedQuery.Substring(0, 100) + "…";
            ToyBox.LogMessage($"ItemPanel search changed: query='{loggedQuery}', results={ItemList.Count}");
        }
        if (!string.Equals(_numberInput.text ?? string.Empty, _lastQuantityText, StringComparison.Ordinal))
            ValidateQuantity(true);
    }

    private void LoadItemData()
    {
#if DEBUGMODE
        System.Diagnostics.Stopwatch stopwatch = new System.Diagnostics.Stopwatch();
        stopwatch.Start();
#endif

        _classifiedItems.Clear();
        _allItems.Clear();
        _searchNames.Clear();
        foreach (var group in _typeList) {
            ItemType mainType = group[0];
            if (!_classifiedItems.ContainsKey(mainType)) {
                _classifiedItems[mainType] = new List<ItemData>();
            }
        }

        var itemsConfig = GameConfig.Instance.ItemDataScriptObject.ItemData;
        foreach (var itemData in itemsConfig) {
            if (itemData == null) continue;
            _allItems.Add(itemData);
            _searchNames[itemData.Uid] = SearchText.Normalize(itemData.GetName(true)) + " " + SearchText.Normalize(itemData.UName);
            foreach (var group in _typeList) {
                ItemType mainType = group[0];
                if ((itemData.Type & mainType) == itemData.Type) {
                    _classifiedItems[mainType].Add(itemData);
                    break; 
                }
            }
        }

        foreach (var list in _classifiedItems.Values) {
            list.Sort((a, b) => a.Piror.CompareTo(b.Piror));
        }
        _allItems.Sort((a, b) => a.Piror.CompareTo(b.Piror));

#if DEBUGMODE
        stopwatch.Stop();
        ToyBox.LogMessage("LoadItemData Execution time: " + stopwatch.ElapsedMilliseconds + "ms");
#endif
    }

    private void UpdateSubToggles(int type)
    {

#if DEBUGMODE
        System.Diagnostics.Stopwatch stopwatch = new System.Diagnostics.Stopwatch();
        stopwatch.Start();
#endif

        var toggles = _subtypeGroup.transform;

        int togglenum = _typeList[type].Length;
        switch(type) {
            case 0:
                toggles.GetChild(1).GetComponentInChildren<TextMeshProUGUI>().text = "武器";
                toggles.GetChild(2).GetComponentInChildren<TextMeshProUGUI>().text = "内甲";
                toggles.GetChild(3).GetComponentInChildren<TextMeshProUGUI>().text = "配饰";
                break;
            case 1:
                toggles.GetChild(1).GetComponentInChildren<TextMeshProUGUI>().text = "外功";
                toggles.GetChild(2).GetComponentInChildren<TextMeshProUGUI>().text = "内功";
                break;
            case 2:
                toggles.GetChild(1).GetComponentInChildren<TextMeshProUGUI>().text = "食物";
                toggles.GetChild(2).GetComponentInChildren<TextMeshProUGUI>().text = "丹药";
                toggles.GetChild(3).GetComponentInChildren<TextMeshProUGUI>().text = "药品";
                toggles.GetChild(4).GetComponentInChildren<TextMeshProUGUI>().text = "配方";
                break;
        }

        for (int i = 0; i < toggles.childCount; i++) {
            toggles.GetChild(i).GetComponent<Toggle>().SetIsOnWithoutNotify(i == 0);
            toggles.GetChild(i).gameObject.SetActive(i < togglenum);
        }

#if DEBUGMODE
        stopwatch.Stop();
        ToyBox.LogMessage("UpdateSubToggles Execution time: " + stopwatch.ElapsedMilliseconds + "ms");
#endif
    }


    private void UpdateItemList(int maintype, int subType = 0)
    {

        if (!_ready || maintype < 0 || maintype >= _typeList.Length) return;
        if (subType < 0 || subType >= _typeList[maintype].Length) return;

#if DEBUGMODE
        System.Diagnostics.Stopwatch stopwatch = new System.Diagnostics.Stopwatch();
        stopwatch.Start();
#endif

        _selectedType = maintype;
        _selectedSubtype = subType;
        _searchStatus.color = new Color(0.83f, 0.87f, 0.92f);
        var type = _typeList[maintype][0];
        if (_query.Length > 0) {
            ItemList = _allItems.Where(x => SearchText.Matches(_searchNames[x.Uid], x.Uid, _query)).ToList();
            _searchStatus.text = $"全局搜索 {ItemList.Count} 项";
        }
        else {
            ItemList = _classifiedItems[type].Where(x =>
                (x.Type & _typeList[maintype][subType]) == x.Type).ToList();
            _searchStatus.text = $"当前分类 {ItemList.Count} 项";
        }

        _infinityScroll.Data = ItemList;

#if DEBUGMODE
        stopwatch.Stop();
        ToyBox.LogMessage("UpdateItemList Execution time: " + stopwatch.ElapsedMilliseconds + "ms");
#endif
    }

    private TextMeshProUGUI CreateStatus(TMP_InputField input, string name, float width)
    {
        // The game's input text can be a different TMP component type. Create the
        // requested concrete component instead of assuming a clone has that type.
        var statusObject = new GameObject(name);
        var status = statusObject.AddComponent<TextMeshProUGUI>();
        statusObject.transform.SetParent(input != null ? input.transform : transform, false);
        try {
            var source = input != null ? input.textComponent : null;
            if (source != null && source.font != null) status.font = source.font;
        }
        catch (Exception exception) {
            ToyBox.LogWarning($"ItemPanel {name}: source font unavailable ({exception.GetType().Name}); using TMP default.");
        }
        try {
            status.raycastTarget = false;
            status.richText = false;
            status.enableAutoSizing = false;
            status.fontSize = 32;
            status.alignment = TextAlignmentOptions.Left;
            status.overflowMode = TextOverflowModes.Overflow;
            status.enableWordWrapping = false;
            status.color = new Color(0.83f, 0.87f, 0.92f);
            var rect = statusObject.GetComponent<RectTransform>();
            if (rect != null) {
                rect.anchorMin = new Vector2(0, 1);
                rect.anchorMax = new Vector2(1, 1);
                rect.pivot = new Vector2(0, 0);
                rect.anchoredPosition = new Vector2(0, 50);
                rect.sizeDelta = new Vector2(0, 42);
            }
        }
        catch (Exception exception) {
            // Cosmetic setup must not abort the rest of ItemPanel.Awake.
            ToyBox.LogWarning($"ItemPanel {name}: status styling incomplete ({exception.GetType().Name}).");
        }
        return status;
    }

    private bool ValidateQuantity(bool refreshItems)
    {
        string rawInput = _numberInput.text ?? string.Empty;
        string input = rawInput.Trim();
        IsQuantityValid = int.TryParse(input, System.Globalization.NumberStyles.None,
            System.Globalization.CultureInfo.InvariantCulture, out int number) && number >= 1 && number <= 9999;
        Number = IsQuantityValid ? number : 0;
        _quantityStatus.text = IsQuantityValid ? $"数量 {Number}（1–9999）" : "请输入 1–9999 整数";
        _quantityStatus.color = IsQuantityValid ? new Color(0.83f, 0.87f, 0.92f) : new Color(1f, 0.45f, 0.38f);
        if (refreshItems) {
            _lastQuantityText = rawInput;
            _infinityScroll?.RefreshVisibleItems();
        }
        return IsQuantityValid;
    }

    public bool TryGetQuantity(out int number)
    {
        bool valid = _ready && isActiveAndEnabled && ValidateQuantity(false);
        number = valid ? Number : 0;
        return valid;
    }

    public void ShowPickupUnavailable(string message)
    {
        _quantityStatus.text = message;
        _quantityStatus.color = new Color(1f, 0.45f, 0.38f);
    }

    public void ShowPickupResult(string itemName, int number, bool confirmed)
    {
        _searchStatus.text = confirmed ? $"已添加 {itemName} ×{number}" : $"已提交 {itemName} ×{number}，请核对背包";
        _searchStatus.color = confirmed ? new Color(0.50f, 0.95f, 0.64f) : new Color(1f, 0.78f, 0.40f);
    }

    private void OnDestroy()
    {
        if (Instance == this) Instance = null;
    }

}
