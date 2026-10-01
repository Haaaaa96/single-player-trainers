// Modified in this research snapshot; see NOTICE.txt for scope.
namespace HaxxToyBox.GUI;

[RegisterInIl2Cpp]
public class PopupPanel : MonoBehaviour
{
    private Color _backgroundColor = new Color(10.0f / 255.0f, 10.0f / 255.0f, 10.0f / 255.0f, 0.6f);

    private GameObject _background;

    public PopupPanel(IntPtr ptr) : base(ptr) { }

    public void Open()
    {
        AddBackground();
    }

    public void Close()
    {
        RemoveBackground();
    }

    private void AddBackground()
    {
        if (_background != null) return;
        _background = new GameObject("PopupBackground");
        var image = _background.AddComponent<Image>();
        image.color = _backgroundColor;
        image.raycastTarget = true;
        _background.transform.SetParent(transform.parent, false);
        var rect = _background.GetComponent<RectTransform>();
        rect.anchorMin = Vector2.zero;
        rect.anchorMax = Vector2.one;
        rect.offsetMin = Vector2.zero;
        rect.offsetMax = Vector2.zero;
        _background.transform.SetSiblingIndex(transform.GetSiblingIndex());
    }

    private void RemoveBackground()
    {
        if (_background == null) return;
        _background.SetActive(false);
        Destroy(_background);
        _background = null;
    }

    private void OnDisable() { RemoveBackground(); }
}
