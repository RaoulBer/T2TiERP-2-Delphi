unit DbxObservationTrace;
interface
uses System.SysUtils, System.Classes;
type
 TAdapterObservationStage=(aosLoadLibrary,aosCreateMethodTable,aosLoadMethods,aosGetDriver,
  aosContextError,aosCreateConnection,aosCheckResult,aosDerivedOpen,aosCapability,
  aosVersion,aosOpenBefore,aosInheritedOpen,aosOpenAfter,aosVendorProperty);
 TAdapterObservationEdge=(aoeEnter,aoeReturn);
procedure InitializeAdapterTrace(const PrivateDirectory: string);
procedure ObserveAdapterStage(Stage: TAdapterObservationStage; Edge: TAdapterObservationEdge;
 Code: Integer=0; HasCode: Boolean=False);
procedure FinishAdapterTrace;
implementation
uses System.IOUtils, System.Hash;
const Names: array[TAdapterObservationStage] of string=(
 'LOAD_DRIVER_LIBRARY','CREATE_METHOD_TABLE','LOAD_METHODS','LOADER_GET_DRIVER',
 'DBX_CONTEXT_ERROR','DRIVER_CREATE_CONNECTION','CHECK_CREATE_RESULT','DERIVED_OPEN',
 'CAPABILITY_PROPERTY','VERSION_PROPERTY','DO_DERIVED_OPEN_BEFORE','INHERITED_DERIVED_OPEN',
 'DO_DERIVED_OPEN_AFTER','GET_VENDOR_PROPERTY');
var Trace: TFileStream; TracePath: string; Healthy: Boolean; Sequence: Integer;
procedure InitializeAdapterTrace(const PrivateDirectory: string);
begin
 Trace:=nil;TracePath:='';Healthy:=False;Sequence:=0;
 try
  if not DirectoryExists(PrivateDirectory) then Exit;
  TracePath:=TPath.Combine(PrivateDirectory,'adapter-observation-private.jsonl');
  if FileExists(TracePath) or DirectoryExists(TracePath) then Exit;
  Trace:=TFileStream.Create(TracePath,fmCreate or fmShareDenyWrite);Healthy:=True;
 except Healthy:=False;end;
end;
procedure ObserveAdapterStage(Stage: TAdapterObservationStage; Edge: TAdapterObservationEdge;
 Code: Integer; HasCode: Boolean);
var Text, CodeText, EdgeText: string; Bytes: TBytes;
begin
 if not Healthy or (Trace=nil) then Exit;
 try
  if (Sequence>=10000) or (Trace.Size>=1048576) then begin Healthy:=False;Exit;end;
  Inc(Sequence);if HasCode then CodeText:=IntToStr(Code) else CodeText:='null';
  if Edge=aoeEnter then EdgeText:='ENTER' else EdgeText:='RETURN';
  Text:='{"event":"adapter_stage","sequence":'+IntToStr(Sequence)+',"stage":"'+Names[Stage]+'","edge":"'+EdgeText+'","numeric_code":'+CodeText+'}'+#10;
  Bytes:=TEncoding.UTF8.GetBytes(Text);Trace.WriteBuffer(Bytes[0],Length(Bytes));
 except Healthy:=False;end;
end;
procedure FinishAdapterTrace;
var Input: TFileStream; Hash: THashSHA2; Buffer: TBytes; Count: Integer; Digest, Status: string; Size: Int64;
begin
 Size:=0;Digest:='';Status:='UNAVAILABLE';
 try
  FreeAndNil(Trace);
  if Healthy and (TracePath<>'') and FileExists(TracePath) then begin
   Input:=TFileStream.Create(TracePath,fmOpenRead or fmShareDenyWrite);
   try
    Size:=Input.Size;Hash:=THashSHA2.Create;SetLength(Buffer,65536);
    repeat Count:=Input.Read(Buffer[0],Length(Buffer));if Count>0 then begin SetLength(Buffer,Count);Hash.Update(Buffer);SetLength(Buffer,65536);end;until Count=0;
    Digest:=Hash.HashAsString;Status:='OBSERVED_PENDING_REVIEW';
   finally Input.Free;end;
  end;
 except Healthy:=False;Status:='UNAVAILABLE';Digest:='';Size:=0;end;
 try
  Writeln('{"event":"adapter_trace_summary","status":"'+Status+'","trace_sha256":"'+Digest+'","trace_bytes":'+IntToStr(Size)+',"records":'+IntToStr(Sequence)+',"sql_queries":0,"qualification":"DIAGNOSTIC_ONLY"}');
 except end;
end;
initialization Trace:=nil;Healthy:=False;Sequence:=0;
finalization Trace.Free;
end.
