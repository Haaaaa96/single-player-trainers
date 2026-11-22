param([Parameter(Mandatory)][string]$LoaderRoot,[Parameter(Mandatory)][string]$Interop,[Parameter(Mandatory)][string]$IndexDirectory,[string]$Out=(Join-Path $PSScriptRoot 'release'))
$ErrorActionPreference='Stop'
$Out=[IO.Path]::GetFullPath($Out)
[IO.Directory]::CreateDirectory($Out) | Out-Null
$core=Join-Path $LoaderRoot 'BepInEx/core'
$runtime=Join-Path $LoaderRoot 'dotnet'
Add-Type -Path "$PSHOME/Microsoft.CodeAnalysis.dll","$PSHOME/Microsoft.CodeAnalysis.CSharp.dll"
function Compile([string]$Name,[string[]]$Sources,[string[]]$References,[string]$Kind,[Microsoft.CodeAnalysis.ResourceDescription[]]$TestResources=@()){
    $trees=[Collections.Generic.List[Microsoft.CodeAnalysis.SyntaxTree]]::new()
    $parse=[Microsoft.CodeAnalysis.CSharp.CSharpParseOptions]::Default
    foreach($source in $Sources){$trees.Add([Microsoft.CodeAnalysis.CSharp.CSharpSyntaxTree]::ParseText([IO.File]::ReadAllText((Join-Path $PSScriptRoot $source)),$parse))}
    $refs=[Collections.Generic.List[Microsoft.CodeAnalysis.MetadataReference]]::new()
    foreach($ref in $References){$refs.Add([Microsoft.CodeAnalysis.MetadataReference]::CreateFromFile([IO.Path]::GetFullPath($ref)))}
    $options=[Microsoft.CodeAnalysis.CSharp.CSharpCompilationOptions]::new([Microsoft.CodeAnalysis.OutputKind]$Kind).WithOptimizationLevel([Microsoft.CodeAnalysis.OptimizationLevel]::Release).WithDeterministic($true)
    $compile=[Microsoft.CodeAnalysis.CSharp.CSharpCompilation]::Create([IO.Path]::GetFileNameWithoutExtension($Name),$trees,$refs,$options)
    $stream=[IO.MemoryStream]::new()
    try{
        if($Name -eq 'RiseAlonePlugin.dll'){
            $indexPath=Join-Path $IndexDirectory 'StoryClips.txt'
            $openIndex=[Func[IO.Stream]]{[IO.File]::OpenRead($indexPath)}.GetNewClosure()
            $choicesPath=Join-Path $IndexDirectory 'ChoiceRisks.tsv'
            $openChoices=[Func[IO.Stream]]{[IO.File]::OpenRead($choicesPath)}.GetNewClosure()
            $taskKeysPath=Join-Path $IndexDirectory 'TaskKeys.tsv'
            $openTaskKeys=[Func[IO.Stream]]{[IO.File]::OpenRead($taskKeysPath)}.GetNewClosure()
            $choiceNamesPath=Join-Path $IndexDirectory 'ChoiceNames.tsv'
            $openChoiceNames=[Func[IO.Stream]]{[IO.File]::OpenRead($choiceNamesPath)}.GetNewClosure()
            $resources=[Microsoft.CodeAnalysis.ResourceDescription[]]@(
                [Microsoft.CodeAnalysis.ResourceDescription]::new('RiseAlone.StoryClips',$openIndex,$false),
                [Microsoft.CodeAnalysis.ResourceDescription]::new('RiseAlone.ChoiceRisks',$openChoices,$false),
                [Microsoft.CodeAnalysis.ResourceDescription]::new('RiseAlone.TaskKeys',$openTaskKeys,$false),
                [Microsoft.CodeAnalysis.ResourceDescription]::new('RiseAlone.ChoiceNames',$openChoiceNames,$false))
            $result=$compile.Emit($stream,$null,$null,$null,$resources,$null,[Threading.CancellationToken]::None)
        }elseif($TestResources.Count){
            $result=$compile.Emit($stream,$null,$null,$null,$TestResources,$null,[Threading.CancellationToken]::None)
        }else{$result=$compile.Emit($stream)}
        if(!$result.Success){throw (($result.Diagnostics | Where-Object Severity -eq Error) -join [Environment]::NewLine)}
        [IO.File]::WriteAllBytes((Join-Path $Out $Name),$stream.ToArray())
    }finally{$stream.Dispose()}
}
$rt=@(Get-ChildItem $runtime -Filter '*.dll' | Where-Object {$_.Name -match '^(System\.|netstandard\.|mscorlib\.)' -and $_.Name -notlike '*.Native.dll'} | ForEach-Object FullName)
$loaderRefs=@('0Harmony','BepInEx.Core','BepInEx.Unity.IL2CPP','Il2CppInterop.Runtime') | ForEach-Object {Join-Path $core "$_.dll"}
$proxyRefs=@('Assembly-CSharp','LitJson','AVProVideo.Runtime','DOTween','ZFBrowser','XNode','Il2Cppmscorlib','Il2CppSystem','UnityEngine.CoreModule','UnityEngine.UI','UnityEngine.UIModule','UnityEngine.TextRenderingModule','UnityEngine.InputLegacyModule','Unity.TextMeshPro','UnityEngine.IMGUIModule') | ForEach-Object {Join-Path $Interop "$_.dll"} | Where-Object {Test-Path $_}
Compile 'RiseAlonePlugin.dll' @('Catalog.cs','StoryActors.cs','ChoiceJournal.cs','PhoneReplay.cs','TaskChoices.cs','TaskNames.cs','ChoiceEffects.cs','ChoiceBadges.cs','MapLabels.cs','MapEligibility.cs','ChoiceTimer.cs','MiniGameAssist.cs','Engine.cs','SwitchSettings.cs','Menu.cs','Plugin.cs') ($rt+$loaderRefs+$proxyRefs) 'DynamicallyLinkedLibrary'
Get-FileHash (Join-Path $Out 'RiseAlonePlugin.dll') | ForEach-Object {"$($_.Hash)  $([IO.Path]::GetFileName($_.Path))"}
