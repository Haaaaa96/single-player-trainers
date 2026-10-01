// Modified in this research snapshot; see NOTICE.txt for scope.
using GameData;
using TMPro;
using WuLin;

namespace HaxxToyBox.GUI;

[RegisterInIl2Cpp]
internal class TraitEntry : MonoBehaviour
{
    private TraitData _data;
    public TraitData Data {
        get => _data;
        set
        {
            if (value == _data || value == null) return;

            _data = value;
            _nameText.text = _data.GetName(true);
            _rankText.text = GetRankText(_data.Rarity);
            _descriptionText.text = _data.GetInfo();
        }
    }

    private TextMeshProUGUI _rankText;
    private TextMeshProUGUI _nameText;
    private TextMeshProUGUI _descriptionText;
    private Button _addButton;

    public TraitEntry(IntPtr ptr) : base(ptr) { }

    private void Awake()
    {
        _rankText = transform.Find("RankText").GetComponent<TextMeshProUGUI>();
        _nameText = transform.Find("NameText").GetComponent<TextMeshProUGUI>();
        _descriptionText = transform.Find("DesText").GetComponent<TextMeshProUGUI>();
        _descriptionText.fontSize = 34;
        _descriptionText.fontSizeMax = 34;
        _descriptionText.fontSizeMin = 28;
        _descriptionText.enableAutoSizing = true;
        _descriptionText.overflowMode = TextOverflowModes.Ellipsis;
        var descriptionRect = _descriptionText.GetComponent<RectTransform>();
        descriptionRect.sizeDelta = new Vector2(descriptionRect.sizeDelta.x, 160);

        _addButton = transform.Find("Button").GetComponent<Button>();
        _addButton.onClick.RemoveAllListeners();
        _addButton.onClick.AddListener(OnClickAdd);
    }

    private string GetRankText(int rank)
    {
        string color;
        switch (rank) {
            case 3:
                color = "orange";
                break;
            case 2:
                color = "purple";
                break;
            case 1:
                color = "#87CEEB"; 
                break;
            default:
                return $"#<size=50>{rank}</size>";
        }

        return $"<color={color}>#<size=50>{rank}</size></color>";
    }

    private void OnClickAdd()
    {
        var character = RolePanel.Instance?.Character;
        if (character == null || Data == null || !RolePanel.Instance.HasCurrentCharacter()) return;

        var traits = character.GetAllTrait();

        if (!traits.Contains(Data)) {
            traits.Add(Data);
            character.SetTraits(traits);
            ToyBox.LogMessage($"Trait added: {character.FullName} / {Data.GetName(false)}");
            TraitPanel.Instance.ShowFeedback("已添加：" + SearchText.Normalize(Data.GetName(false)));
            RolePanel.Instance.UpdateRoleInfo();
        }
        else TraitPanel.Instance.ShowFeedback("已拥有：" + SearchText.Normalize(Data.GetName(false)));
    }   
}

public class TraitDelEntry : MonoBehaviour
{
    private TraitData traitData;

    public TextMeshProUGUI nameText;
    public Button delButton;

    static TraitDelEntry()
    {
        ClassInjector.RegisterTypeInIl2Cpp<TraitDelEntry>();
    }

    public TraitDelEntry(IntPtr ptr) : base(ptr) { }

    private void Awake()
    {
        nameText = transform.Find("Text").GetComponent<TextMeshProUGUI>();
        delButton = transform.Find("DelButton").GetComponent<Button>();
        delButton.onClick.RemoveAllListeners();
        delButton.onClick.AddListener(OnClickDel);
    }

    public void SetTrait(TraitData data)
    {
        traitData = data;
        nameText.text = data.GetName(true);
    }

    private void OnClickDel()
    {
        var character = RolePanel.Instance?.Character;
        if (character == null || traitData == null || !RolePanel.Instance.HasCurrentCharacter()) return;

        var traits = character.GetAllTrait();

        if (traits.Contains(traitData)) {
            traits.Remove(traitData);
            character.SetTraits(traits);
            ToyBox.LogMessage($"Trait removed: {character.FullName} / {traitData.GetName(false)}");

            RolePanel.Instance.UpdateRoleInfo();
        }
    }
}
