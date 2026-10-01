// Modified in this research snapshot; see NOTICE.txt for scope.
using GameData;
using TMPro;
using WuLin;
using WuLin.GameFrameworks;

namespace HaxxToyBox.GUI;

[RegisterInIl2Cpp]
internal class MartialEntry : MonoBehaviour
{
    private KungfuData _data;
    public KungfuData Data {
        get => _data;
        set
        {
            bool changed = value != _data;
            _data = value;
            try {
                if (changed && _icon != null) _icon.sprite = _data == null ? null : GetIcon(_data.Icon);
                RefreshLearnState();
            }
            catch (Exception exception) {
                ShowReadFailure(exception);
            }
        }
    }

    private Button _button;
    private Image _icon;
    private TextMeshProUGUI _nameText;
    private TextMeshProUGUI _buttonText;
    private bool _learning;
    private string _lastReadError;

    public MartialEntry(IntPtr ptr) : base(ptr) { }

    private void Awake()
    {
        _nameText = transform.Find("NameText").GetComponent<TextMeshProUGUI>();
        _icon = transform.Find("Icon").GetComponent<Image>();

        _button = transform.Find("Button").GetComponent<Button>();
        _buttonText = _button.GetComponentInChildren<TextMeshProUGUI>();
        if (_button.GetComponent<FadeButtonWrapper>() == null) _button.gameObject.AddComponent<FadeButtonWrapper>();
        _button.onClick.RemoveAllListeners();
        _button.onClick.AddListener(OnClickAdd);
        RefreshLearnState();
    }

    public void OnClickAdd()
    {
        var panel = MartialPanel.Instance;
        var character = panel?.Character;
        var data = _data;
        if (_learning || !isActiveAndEnabled || panel == null || !panel.isActiveAndEnabled || data == null) return;
        _learning = true;
        _button.interactable = false;
        bool attempted = false;
        bool confirmed = false;
        try {
            // Check the live party and selection immediately before the only write.
            if (character == null || panel.Character == null || panel.Character.Pointer != character.Pointer ||
                !MartialPanel.IsCurrentTeamMember(character)) {
                SetFeedback("角色已失效", false);
                ToyBox.LogWarning("Martial learning refused: selected character is no longer in the current party.");
                return;
            }
            if (character.GetKungfuById(data.Uid) != null) {
                MartialPanel.ConfirmLearningReadback(character.Pointer, data.Uid);
                SetFeedback("已学", false);
                return;
            }
            if (MartialPanel.IsLearningUnconfirmed(character.Pointer, data.Uid)) {
                SetFeedback("学习结果待核验", false);
                return;
            }
            MartialPanel.MarkLearningUnconfirmed(character.Pointer, data.Uid);
            attempted = true;
            character.InstantLearnKungfu(data, 1, true);
            if (character.GetKungfuById(data.Uid) == null) {
                SetFeedback("学习未确认", false);
                ToyBox.LogWarning($"Martial learning returned without a learned entry: kungfu={data.Uid}.");
                return;
            }
            confirmed = true;
            MartialPanel.ConfirmLearningReadback(character.Pointer, data.Uid);
            SetFeedback("已学", false);
            ToyBox.LogMessage($"Martial learned: character={character.FullName}, kungfu={data.Uid} ({data.UName}).");
            panel.RefreshEntries();
        }
        catch (Exception ex) {
            SetFeedback(confirmed ? "已学" : attempted ? "学习结果待核验" : "暂不可学习", false);
            ToyBox.LogWarning($"Martial learning {(confirmed ? "confirmed, display refresh failed" : attempted ? "result unconfirmed" : "refused before write")}: {ex.Message}");
        }
        finally {
            _learning = false;
        }
    }

    private void RefreshLearnState()
    {
        if (_button == null || _nameText == null) return;
        try {
            var character = MartialPanel.Instance?.Character;
            if (_data == null) {
                _nameText.text = "";
                _button.interactable = false;
                return;
            }
            if (!MartialPanel.IsCurrentTeamMember(character)) {
                SetFeedback("未选择角色", false);
                return;
            }
            bool learned = character.GetKungfuById(_data.Uid) != null;
            if (learned) MartialPanel.ConfirmLearningReadback(character.Pointer, _data.Uid);
            bool unconfirmed = !learned && MartialPanel.IsLearningUnconfirmed(character.Pointer, _data.Uid);
            SetFeedback(learned ? "已学" : unconfirmed ? "学习结果待核验" : "学习", !learned && !unconfirmed && !_learning);
            _lastReadError = null;
        }
        catch (Exception exception) {
            ShowReadFailure(exception);
        }
    }

    [Il2CppInterop.Runtime.Attributes.HideFromIl2Cpp]
    private void ShowReadFailure(Exception exception)
    {
        // Do not read failing native character/data getters while reporting failure.
        if (_button != null) _button.interactable = false;
        if (_buttonText != null) _buttonText.text = "读取失败";
        if (_nameText != null) _nameText.text = "读取失败（请切页重读）";
        string error = exception.GetType().Name + ": " + exception.Message;
        if (error == _lastReadError) return;
        _lastReadError = error;
        ToyBox.LogWarning("Martial entry read failed; only this entry is disabled: " + error);
    }

    private void SetFeedback(string message, bool canLearn)
    {
        if (_buttonText != null) _buttonText.text = message;
        if (_nameText != null && _data != null) {
            _nameText.text = GetRichText(_data.UName, _data.Rarity) + (message == "学习" ? "" : $"（{message}）");
        }
        if (_button != null) _button.interactable = canLearn;
    }


    private string GetRichText(string text, int rarity)
    {
        string color;
        switch (rarity) {
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
                return text;
        }

        return $"<color={color}>{text}</color>";
    }

    private Sprite GetIcon(string path)
    {
        Sprite sprite = null;
        try {
            sprite = ResourceManager.Instance.GetSprite("UI/Icons/Kungfu/" + path + ".png");
        }
        catch { }

        if (sprite == null) {
            sprite = ResourceManager.Instance.GetSprite("UI/Icons/Kungfu/Default.png");
        }
        return sprite;
    }

}
