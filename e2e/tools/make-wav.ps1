# Decodes an audio file (MP3 fixture) to PCM WAV with Windows Media Foundation (Windows.Media.Transcoding),
# for the fake microphone. Usage: make-wav.ps1 <in> <out>
param([string]$InPath, [string]$OutPath)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Media.Transcoding.MediaTranscoder, Windows.Media.Transcoding, ContentType = WindowsRuntime]
$null = [Windows.Media.MediaProperties.MediaEncodingProfile, Windows.Media.MediaProperties, ContentType = WindowsRuntime]

$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
$asTaskProgress = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncActionWithProgress`1' })[0]
function Await($op, [Type]$type) { $t = $asTaskGeneric.MakeGenericMethod($type).Invoke($null, @($op)); $t.Wait(); $t.Result }
function AwaitProgress($op) { $t = $asTaskProgress.MakeGenericMethod([double]).Invoke($null, @($op)); $t.Wait() }

$inFile = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync((Resolve-Path $InPath).Path)) ([Windows.Storage.StorageFile])
$outDir = Await ([Windows.Storage.StorageFolder]::GetFolderFromPathAsync((Split-Path -Parent $OutPath))) ([Windows.Storage.StorageFolder])
$outFile = Await ($outDir.CreateFileAsync((Split-Path -Leaf $OutPath), [Windows.Storage.CreationCollisionOption]::ReplaceExisting)) ([Windows.Storage.StorageFile])

# PCM WAV with the encoder's default format (setting a custom sample rate makes Media Foundation refuse).
$profile = [Windows.Media.MediaProperties.MediaEncodingProfile]::CreateWav([Windows.Media.MediaProperties.AudioEncodingQuality]::Medium)
$transcoder = New-Object Windows.Media.Transcoding.MediaTranscoder
$inStream = Await ($inFile.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$outStream = Await ($outFile.OpenAsync([Windows.Storage.FileAccessMode]::ReadWrite)) ([Windows.Storage.Streams.IRandomAccessStream])
$prep = Await ($transcoder.PrepareStreamTranscodeAsync($inStream, $outStream, $profile)) ([Windows.Media.Transcoding.PrepareTranscodeResult])
if (-not $prep.CanTranscode) { throw "Cannot transcode: $($prep.FailureReason)" }
AwaitProgress ($prep.TranscodeAsync())
$outStream.Dispose(); $inStream.Dispose()
"wrote $OutPath ($((Get-Item $OutPath).Length) bytes)"
