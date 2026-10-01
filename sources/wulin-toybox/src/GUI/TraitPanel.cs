// Modified in this research snapshot; see NOTICE.txt for scope.
using GameData;

using TMPro;
using WuLin;
namespace HaxxToyBox.GUI;

[RegisterInIl2Cpp]
internal class TraitPanel : MonoBehaviour
{
    //private bool needUpdate = true;

    private InfinityScrollTraitData _infinityScroll;
    private TMP_InputField _search;
    private TextMeshProUGUI _status;
    private string _lastQuery;

    public PopupPanel Popup;

    public List<TraitData> Traits;

    public static TraitPanel Instance { get; private set; }

    public TraitPanel(IntPtr ptr) : base(ptr) { }

    private void Awake()
    {
        Instance = this;

        Popup = gameObject.AddComponent<PopupPanel>();

        var close = transform.Find("PopupBase/Top/CloseButton").GetComponent<Button>();
        close.gameObject.AddComponent<FadeButtonWrapper>();
        close.onClick.AddListener(() => {
            Hide();
        });

        var scrollView = transform.Find("ScrollView").gameObject;
        var entryPrefab = transform.Find("ScrollView/Viewport/EntryPrefab").gameObject;
        var rowRect = entryPrefab.GetComponent<RectTransform>();
        rowRect.sizeDelta = new Vector2(rowRect.sizeDelta.x, 180);
        entryPrefab.AddComponent<TraitEntry>();
        _infinityScroll = scrollView.AddComponent<InfinityScrollTraitData>();
        _infinityScroll.ItemPrefab = entryPrefab;
        _infinityScroll.SpaceY = 10;
        _search = InputBinding.Find(transform.Find("InputField - Single"));
        if (_search != null) {
            _search.SetTextWithoutNotify("");
            _search.onValueChanged.RemoveAllListeners();
            _search.onEndEdit.RemoveAllListeners();
            _search.onValueChanged.AddListener((string value) => Filter(value));
            var hint = _search.placeholder?.GetComponent<TextMeshProUGUI>();
            if (hint != null) hint.text = "搜索天赋名称 / ID";
            _search.gameObject.SetActive(true);
        }
        var statusObject = new GameObject("TraitStatus");
        statusObject.transform.SetParent(transform, false);
        _status = statusObject.AddComponent<TextMeshProUGUI>();
        var label = transform.Find("PopupBase/Top").GetComponentInChildren<TMP_Text>();
        if (label != null) _status.font = label.font;
        _status.fontSize = 32;
        _status.raycastTarget = false;
        var statusRect = _status.GetComponent<RectTransform>();
        statusRect.anchorMin = new Vector2(0, 0);
        statusRect.anchorMax = new Vector2(1, 0);
        statusRect.pivot = new Vector2(0, 0);
        statusRect.anchoredPosition = new Vector2(900, 35);
        statusRect.sizeDelta = new Vector2(-930, 40);
    }
   
    private void Start()
    {
        var traitDB = BaseDataClass.GetGameData<TraitDataScriptObject>().data;

        Traits = new List<TraitData>();
        foreach (var trait in traitDB.Values) {
            Traits.Add(trait);
        }
        Traits.Sort((a, b) => b.Rarity.CompareTo(a.Rarity));

        Filter(_search?.text ?? "");
        // infinityScroll.SetTotalItems(traits.Count);
    }

    public void Show()
    {
        gameObject.SetActive(true);
        Popup.Open();

        //if (needUpdate) {
        //    UpdateTraitList();
        //}
    }

    public void Hide()
    {
        Popup.Close();
        gameObject.SetActive(false);

        RolePanel.Instance.UpdateRoleInfo();
    }

    private void Filter(string query)
    {
        if (Traits == null) return;
        query = SearchText.Normalize(query);
        if (_lastQuery == query) return;
        _lastQuery = query;
        var results = Traits.Where(t => SearchText.Matches(t.GetName(false), t.Uid, query)).ToList();
        _infinityScroll.Data = results;
        ShowFeedback($"{results.Count} 项天赋 · 点击添加");
        ToyBox.LogMessage($"Trait search: {query} -> {results.Count}");
    }

    public void ShowFeedback(string message)
    {
        if (_status != null) _status.text = message;
    }

    private void UpdateTraitList()
    {
        //for (int i = 0; i < traits.Count; i++) {
        //    var trait = traits[i];
        //    GameObject entry = null;
        //    if (i >= scrollView.childCount) {
        //        entry = Instantiate(entryPrefab, scrollView);
        //    }
        //    else {
        //        entry = scrollView.GetChild(i).gameObject;
        //    }
        //    entry.SetActive(true);
        //    entry.GetComponent<TraitEntry>().SetTrait(trait);
        //}

        //for (int i = traits.Count; i < scrollView.childCount; i++) {
        //    scrollView.GetChild(i).gameObject.SetActive(false);
        //}
    }
}
