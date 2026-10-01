using TMPro;

namespace HaxxToyBox.GUI;

// The original prefab contains an empty outer TMP_InputField and a working
// nested TMP_InputField. Bind the actual text owner, not the first component.
internal static class InputBinding
{
    public static TMP_InputField Find(Transform root)
    {
        if (root == null) throw new InvalidOperationException("Input root is missing.");
        var inputs = root.GetComponentsInChildren<TMP_InputField>(true);
        var live = inputs.Where(input => input.textComponent != null).ToArray();
        if (live.Length != 1)
            throw new InvalidOperationException($"Expected one bound input under {root.name}; found {live.Length}.");
        foreach (var input in inputs)
            if (input.Pointer != live[0].Pointer && input.textComponent == null) input.enabled = false;
        return live[0];
    }
}
