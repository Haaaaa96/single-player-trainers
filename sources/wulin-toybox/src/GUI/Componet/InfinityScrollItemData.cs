// Modified in this research snapshot; see NOTICE.txt for scope.
using GameData;

namespace HaxxToyBox.GUI;

// Local changes (2026-09-30): refresh supplied lists and clear recycled item bindings.

[RegisterInIl2Cpp]
internal class InfinityScrollItemData : InfinityScrollBase
{
    private List<ItemData> _data;

    public List<ItemData> Data {
        get => _data;
        set
        {
            _data = value;
            UpdateContentSize();
        }
    }
    public override int TotalItems => _data?.Count ?? 0;

    public InfinityScrollItemData(IntPtr ptr) : base(ptr) { }

    protected override void UpdateItems(int startIndex)
    {
        for (int i = 0; i < _items.Count; i++)
        {
            int realIndex = i + startIndex;

            if (realIndex < 0 || realIndex >= TotalItems) {
                var emptyEntry = _items[i].GetComponent<ItemEntry>();
                if (emptyEntry != null) emptyEntry.Data = null;
                _items[i].SetActive(false);
                continue;
            }

            _items[i].SetActive(true);

            RectTransform itemRect = _items[i].GetComponent<RectTransform>();
            int row = i / Columns;
            int column = i % Columns;

            itemRect.anchoredPosition = new Vector2(_itemWidth * column, -(row * _itemHeight) - startIndex / Columns * _itemHeight);
            var entry = _items[i].GetComponent<ItemEntry>();
            if (entry != null) {
                entry.Data = Data[realIndex];
            }
        }
    }
}
