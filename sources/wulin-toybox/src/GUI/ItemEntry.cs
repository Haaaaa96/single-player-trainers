// Modified in this research snapshot; see NOTICE.txt for scope.
using GameData;
using TMPro;
using WuLin;

namespace HaxxToyBox.GUI;

// Local changes (2026-09-30): clear recycled bindings and validate the active item/quantity before pickup.
// Original HaxxToyBox license is preserved in LICENSE.txt.

[RegisterInIl2Cpp]
internal class ItemEntry : MonoBehaviour
{
    private ItemData _data;
    public ItemData Data {
        get => _data;
        set
        {
            if (_button != null) _button.interactable = value != null && ItemPanel.Instance?.IsQuantityValid == true;
            if (value == _data) return;

            _data = value;
            if (_nameText != null) _nameText.text = _data?.GetName(true) ?? string.Empty;
            if (_icon != null) _icon.sprite = _data?.GetIcon();
        }
    }

    private Button _button;
    private Image _icon;
    private TextMeshProUGUI _nameText;

    public ItemEntry(IntPtr ptr) : base(ptr) { }

    private void Awake()
    {
        _nameText = transform.Find("Text").GetComponent<TextMeshProUGUI>();
        _icon = transform.Find("Button/Icon").GetComponent<Image>();

        _button = transform.Find("Button").GetComponent<Button>();
        if (_button.GetComponent<FadeButtonWrapper>() == null) _button.gameObject.AddComponent<FadeButtonWrapper>();
        _button.onClick.RemoveAllListeners();
        _button.onClick.AddListener(OnClick);
    }

    public void OnClick()
    {
        var panel = ItemPanel.Instance;
        if (_data == null || !gameObject.activeInHierarchy || panel == null || !panel.TryGetQuantity(out int number)) return;
        if (!panel.ItemList.Any(item => item != null && item.Pointer == _data.Pointer)) {
            panel.ShowPickupUnavailable("物品列表已更新，请重新选择");
            return;
        }
        var team = PlayerTeamManager.HasInstance ? PlayerTeamManager.Instance : null;
        var inventory = team?.TeamInventory;
        if (inventory == null) {
            panel.ShowPickupUnavailable("尚未读取有效队伍背包");
            return;
        }

        var item = _data;
        string itemName = SearchText.Normalize(_nameText?.text ?? item.UName);
        bool beforeKnown = TryReadCount(inventory, item.Uid, out int before);
        bool submitted = false;
        try {
            var pack = new GameItemPack();
            if (!pack.AddItem(item, number)) {
                panel.ShowPickupUnavailable("物品准备失败，尚未提交");
                return;
            }
            submitted = true;
            team.PickupPack(pack);
            var currentTeam = PlayerTeamManager.HasInstance ? PlayerTeamManager.Instance : null;
            var currentInventory = currentTeam?.TeamInventory;
            int after = 0;
            bool sameInventory = currentTeam != null && currentTeam.Pointer == team.Pointer
                && currentInventory != null && currentInventory.Pointer == inventory.Pointer;
            bool afterKnown = sameInventory && TryReadCount(currentInventory, item.Uid, out after);
            bool confirmed = beforeKnown && afterKnown && (long)after - before == number;
            panel.ShowPickupResult(itemName, number, confirmed);
            ToyBox.LogMessage($"Item pickup: id={item.Uid}, requested={number}, before={(beforeKnown ? before.ToString() : "unknown")}, after={(afterKnown ? after.ToString() : "unknown")}, confirmed={confirmed}");
        }
        catch (Exception exception) {
            if (submitted) panel.ShowPickupResult(itemName, number, false);
            else panel.ShowPickupUnavailable("物品准备失败，尚未提交");
            ToyBox.LogWarning($"Item pickup: id={item.Uid}, submitted={submitted}, result not confirmed; no retry. {exception.GetType().Name}: {exception.Message}");
        }
    }

    private static bool TryReadCount(GameItemPack inventory, int itemId, out int count)
    {
        count = 0;
        try {
            // Verified current native API sums matching Uid quantities across Contents.
            count = inventory.GetItemCountById(itemId);
            return count >= 0;
        }
        catch (Exception exception) {
            ToyBox.LogWarning($"Item count unavailable: id={itemId}, {exception.GetType().Name}");
            return false;
        }
    }
}
