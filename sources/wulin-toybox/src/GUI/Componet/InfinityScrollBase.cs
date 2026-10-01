// Modified in this research snapshot; see NOTICE.txt for scope.
namespace HaxxToyBox.GUI;

// Local changes (2026-09-30): immediate short/empty refresh and corrected layout dimensions.
// Original HaxxToyBox license is preserved in LICENSE.txt.
// Currently, Il2CppInterop does not support registering
// template/generic classes to Il2Cpp. 
internal abstract class InfinityScrollBase : MonoBehaviour
{
    protected ScrollRect _scrollRect;
    protected List<GameObject> _items = new List<GameObject>();
    protected float _itemHeight;
    protected float _itemWidth;
    protected int _rowsVisibleInView;
    private bool _initialized;
    private int _lastStartIndex = -1;

    public float SpaceX = 0;
    public float SpaceY = 0;
    public GameObject ItemPrefab;
    public int Columns = 1;

    public virtual int TotalItems { get; }

    //public InfinityScrollBase() 
    //{
    //    ClassInjector.RegisterTypeInIl2Cpp<InfinityScrollBase>();
    //}

    public InfinityScrollBase(IntPtr ptr) : base(ptr) { }

    protected virtual void Awake()
    {
        _scrollRect = GetComponent<ScrollRect>();
    }

    protected void UpdateContentSize()
    {
        // Data can arrive before Unity calls Start and the pool exists.
        if (!_initialized) return;
        RectTransform contentRect = _scrollRect.content;
        contentRect.sizeDelta = new Vector2(contentRect.sizeDelta.x, (TotalItems + Columns - 1) / Columns * _itemHeight);
        _scrollRect.StopMovement();
        contentRect.anchoredPosition = new Vector2(contentRect.anchoredPosition.x, 0);
        _scrollRect.SetVerticalNormalizedPosition(1);
        RefreshVisibleItems();
    }

    protected virtual void Start()
    {
        Columns = Mathf.Max(1, Columns);
        Canvas.ForceUpdateCanvases();
        InitializeItemDimensions();
        InitializeVisibleRows();
        InitializeItems();
        _initialized = true;
        UpdateContentSize();
    }

    protected void InitializeItemDimensions()
    {
        var itemRect = ItemPrefab.GetComponent<RectTransform>();
        _itemHeight = Mathf.Max(1, itemRect.rect.height + SpaceY);
        _itemWidth = Mathf.Max(1, itemRect.rect.width + SpaceX);
    }

    protected void InitializeVisibleRows()
    {
        _rowsVisibleInView = Mathf.Max(1, Mathf.CeilToInt(_scrollRect.viewport.rect.height / _itemHeight)) + 2;
    }

    protected void InitializeItems()
    {
        for (int i = _items.Count; i < _rowsVisibleInView * Columns; i++) {
            GameObject item = Instantiate(ItemPrefab, _scrollRect.content);
            _items.Add(item);
        }

    }

    protected virtual void LateUpdate()
    {
        if (!_initialized) return;
        int previousRows = _rowsVisibleInView;
        InitializeVisibleRows();
        if (previousRows != _rowsVisibleInView) {
            InitializeItems();
            RefreshVisibleItems();
        }
        else if (GetStartIndex() != _lastStartIndex) RefreshVisibleItems();
    }

    public void RefreshVisibleItems()
    {
        if (!_initialized) return;
        _lastStartIndex = GetStartIndex();
        // Always update, including zero items and the incomplete final row.
        UpdateItems(_lastStartIndex);
    }

    private int GetStartIndex()
    {
        int row = Mathf.FloorToInt(_scrollRect.content.anchoredPosition.y / _itemHeight);
        int lastRow = Mathf.Max(0, (TotalItems - 1) / Columns);
        return Mathf.Clamp(row, 0, lastRow) * Columns;
    }

    // The method should ideally be defined as abstract.
    // However, due to limitations with Il2cppInterop, we can't declare it as such.
    protected virtual void UpdateItems(int startIndex) 
    {
        // DO NOTHING
        return;
    }
}
