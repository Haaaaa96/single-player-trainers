// Modified in this research snapshot; see NOTICE.txt for scope.
using BepInEx;
using HaxxToyBox.Config;
using HaxxToyBox.GUI;
using HaxxToyBox.Utilities;
using System.Reflection;
using WuLin;
using InputManager = UniverseLib.Input.InputManager;


namespace HaxxToyBox;

[RegisterInIl2Cpp]
internal class ToyBoxBehaviour : MonoBehaviour
{
    public static class Constants
    {
        public const string BundleRes = "Assets.toybox";
        public const string BundlePath = "/HaxxToyBox/AssetBundle/toybox";
        public const string AssetName = "ToyBoxCanvas";
    }

    private bool _initialized = false;

    private List<GameObject> Panels = new();

    public static ToyBoxBehaviour Instance { get; private set; }
    public GameObject GUICanvas { get; private set; }

    public ToyBoxBehaviour(IntPtr ptr) : base(ptr) { }
    
    public static void Setup()
    {
        Instance = new GameObject("ToyBoxBehaviour").AddComponent<ToyBoxBehaviour>();
        DontDestroyOnLoad(Instance.gameObject);
        Instance.gameObject.hideFlags |= HideFlags.HideAndDontSave;
    }
    
    private void Awake()
    {
        LoadAsset();
        // StartCoroutine(Init());
        SetupUI();
    }

    //private IEnumerator Init()
    //{
    //    LoadAsset();
    //}
    private void OnEnable()
    {
        // The persistent behaviour is not the panel; only an open canvas owns a pause.
    }

    private void OnDisable()
    {
        SetBlock(false);
    }

    private void OnDestroy() { SetBlock(false); }

    private void SetBlock(bool block)
    {
        if (GameTimer.HasInstance) {
            if (block)
                GameTimer.Instance.AddOrSetTimeScale(this, 0);
            else
                GameTimer.Instance.RemoveTimeScale(this);
        }
        if (InGameTimeManager.HasInstance) {
            if (block)
                InGameTimeManager.RegisterTimeBlocker("HaxxToyBox");
            else
                InGameTimeManager.UnRegisterTimeBlocker("HaxxToyBox");
        }
    }

    private void LoadAsset(bool fromFile=false)
    {
        if (fromFile)
            LoadAssetFromFile();
        else
            LoadAssetFromEmbedded();
    }

    private void LoadAssetFromFile()
    {
        if (!File.Exists(Paths.PluginPath + Constants.BundlePath)) {
            ToyBox.LogWarning("Skipping AssetBundle Loading - AssetBundle Doesn't Exist at: " + Paths.PluginPath + Constants.BundlePath);
            return;
        }

        ToyBox.LogMessage($"Trying to load {Constants.AssetName} from {Constants.BundlePath} ...");
        var guiAsset = AssetBundle.LoadFromFile(Paths.PluginPath + Constants.BundlePath);
        if (guiAsset == null) {
            ToyBox.LogMessage("AssetBundle Failed to Load!");
            return;
        }

        ToyBox.LogMessage("Trying to Load Prefab...");
        var guiPrefab = guiAsset.LoadAsset<GameObject>(Constants.AssetName);
        if (guiPrefab != null) {
            ToyBox.LogMessage("Asset Loaded! Trying to Instantiate Prefab...");
            GUICanvas = Instantiate(guiPrefab);
            GUICanvas.name = "ToyBoxCanvas";
            DontDestroyOnLoad(GUICanvas);
            GUICanvas.SetActive(false);

            //trainerGUI = GUICanvas.AddComponent<TrainerGUI>();

            _initialized = true;
        }
        else {
            ToyBox.LogMessage("Failed to Load Asset!");
        }
    }

    private void LoadAssetFromEmbedded()
    {
        ToyBox.LogMessage($"Trying to load {Constants.AssetName} from embedded resources...");

        var assembly = Assembly.GetExecutingAssembly();
        var resourceName = $"{assembly.GetName().Name}.{Constants.BundleRes}";

        using (Stream stream = assembly.GetManifestResourceStream(resourceName)) {
            if (stream == null) {
                ToyBox.LogWarning($"Asset bundle not found in embedded resources: {resourceName}");
                return;
            }

            byte[] buffer = new byte[stream.Length];
            stream.Read(buffer, 0, buffer.Length);

            var guiAsset = AssetBundle.LoadFromMemory(buffer);
            if (guiAsset == null) {
                ToyBox.LogMessage("AssetBundle Failed to Load from Memory!");
                return;
            }

            ToyBox.LogMessage("Trying to Load Prefab...");
            var guiPrefab = guiAsset.LoadAsset<GameObject>(Constants.AssetName);
            if (guiPrefab != null) {
                ToyBox.LogMessage("Asset Loaded! Trying to Instantiate Prefab...");
                GUICanvas = Instantiate(guiPrefab);
                GUICanvas.name = "ToyBoxCanvas";
                DontDestroyOnLoad(GUICanvas);
                GUICanvas.SetActive(false);

                //trainerGUI = GUICanvas.AddComponent<TrainerGUI>();

                _initialized = true;
            }
            else {
                ToyBox.LogMessage("Failed to Load Asset!");
            }
        }
    }

    private void SetupUI()
    {
        UiPolish.Apply(GUICanvas);
        UiPolish.AddVersionLabel(GUICanvas);
        var buttonBot = GUICanvas.transform.Find("Buttons Bottom");
        foreach (var child in buttonBot) {
            var button = child.Cast<Transform>().Find("Button").GetComponent<Button>();
            button.gameObject.AddComponent<FadeButtonWrapper>();

            var panelName = $"{child.Cast<Transform>().name}Panel";
            var panel = GUICanvas.transform.Find(panelName)?.gameObject;
            if (panel != null) {
                Panels.Add(panel);
                button.onClick.AddListener(() => {
                    for (int i = 0; i < Panels.Count; i++) {
                        Panels[i].SetActive(false);
                    }
                    panel.SetActive(true);
                });
            }
        }
        
        var rolePanel = GUICanvas.transform.Find("RolePanel").gameObject;
        rolePanel.AddComponent<RolePanel>();

        var traitPanel = GUICanvas.transform.Find("TraitPanel").gameObject;
        traitPanel.AddComponent<TraitPanel>();

        var addTraitButton = rolePanel.transform.Find("AddTrait").GetComponent<Button>();
        addTraitButton.gameObject.AddComponent<FadeButtonWrapper>();
        addTraitButton.onClick.AddListener(() => {
            traitPanel.GetComponent<TraitPanel>().Show();
        });

        var itemPanel = GUICanvas.transform.Find("ItemPanel").gameObject;
        itemPanel.AddComponent<ItemPanel>();

        var miscPanel = GUICanvas.transform.Find("MiscPanel").gameObject;
        miscPanel.AddComponent<MiscPanel>();

        var martialPanel = GUICanvas.transform.Find("MartialPanel").gameObject;
        martialPanel.AddComponent<MartialPanel>();
    }


    public void ShowCanvas()
    {
        if (!PlayerTeamManager.HasInstance || PlayerTeamManager.Instance.TeamSize == 0) {
            ToyBox.LogWarning("请先进入存档，待角色出现后再打开修改器。");
            return;
        }
        GUICanvas.SetActive(true);
        SetBlock(true);
    }

    public void HideCanvas()
    {
        // Close the owned modal before its parent canvas, so the next opening
        // cannot retain a visible popup without its input-blocking backdrop.
        if (TraitPanel.Instance != null && TraitPanel.Instance.gameObject.activeSelf)
            TraitPanel.Instance.Hide();
        GUICanvas.SetActive(false);
        SetBlock(false);
    }

    public void Update()
    {
        if (_initialized && !MiscPanel.IsEditingInput() && InputManager.GetKeyDown(ConfigManager.Canvas_Toggle.Value)) {
            if (GUICanvas.active)
                HideCanvas();
            else 
                ShowCanvas();
        }

        if (InputManager.GetKeyDown(ConfigManager.Recover_Toggle.Value)) {
            MiscPanel.RecoverAll();
        }

        if (InputManager.GetKeyDown(ConfigManager.SpeedUp_Toggle.Value)) {
            MiscPanel.SpeedUp();
        }

        if (InputManager.GetKeyDown(ConfigManager.SpeedDown_Toggle.Value)) {
            MiscPanel.SpeedDown();
        }

        //if (InputManager.GetKeyDown(KeyCode.F2)) {
        //    MartialPanel.WriteMartialToCSV("MartialData.csv");
        //}
    }

}
