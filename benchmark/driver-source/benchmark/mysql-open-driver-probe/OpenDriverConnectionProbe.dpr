program OpenDriverConnectionProbe;
{$APPTYPE CONSOLE}
uses
 System.SysUtils, System.Classes, System.IOUtils, System.JSON, System.Hash,
 Winapi.Windows, Data.DB, Data.SqlExpr,
 UOpenDriverConnection in 'UOpenDriverConnection.pas';
function SidString(Sid: Pointer; var Text: PWideChar): BOOL; stdcall;
 external 'advapi32.dll' name 'ConvertSidToStringSidW';
function SecurityDescriptor(Text: PWideChar; Revision: DWORD; var Descriptor: Pointer; Size: Pointer): BOOL; stdcall;
 external 'advapi32.dll' name 'ConvertStringSecurityDescriptorToSecurityDescriptorW';
type TUserData = record Sid: Pointer; Attributes: DWORD; end;
     PUserData = ^TUserData;
var Stage, OutputDir: string; Connection: TOpenDriverConnection; Failed: Boolean; QueryCount: Integer;
function CurrentSid: string;
var Token: THandle; Needed: DWORD; Buffer: TBytes; Text: PWideChar;
begin
 Token:=0;Text:=nil;
 if not OpenProcessToken(GetCurrentProcess,TOKEN_QUERY,Token) then RaiseLastOSError;
 try
  Needed:=0;GetTokenInformation(Token,TokenUser,nil,0,Needed);
  if Needed=0 then RaiseLastOSError;
  SetLength(Buffer,Needed);
  if not GetTokenInformation(Token,TokenUser,@Buffer[0],Needed,Needed) then RaiseLastOSError;
  if not SidString(PUserData(@Buffer[0])^.Sid,Text) then RaiseLastOSError;
  try Result:=string(Text);finally LocalFree(HLOCAL(Text));end;
 finally CloseHandle(Token);end;
end;
procedure PreparePrivateDirectory;
var SD: Pointer; SA: TSecurityAttributes; SDDL, Canonical: string;
begin
 if ParamCount<>1 then raise Exception.Create('Diagnostic output input required');
 Canonical:=TPath.GetFullPath(ParamStr(1));
 if not SameText(Copy(Canonical,1,16),'C:\build-inputs\') then
  raise Exception.Create('Diagnostic private output path invalid');
 if DirectoryExists(Canonical) or FileExists(Canonical) then
  raise Exception.Create('Diagnostic private output already exists');
 SDDL:='D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;FA;;;'+CurrentSid+')';SD:=nil;
 if not SecurityDescriptor(PWideChar(SDDL),1,SD,nil) then RaiseLastOSError;
 try
  FillChar(SA,SizeOf(SA),0);SA.nLength:=SizeOf(SA);SA.lpSecurityDescriptor:=SD;
  if not CreateDirectory(PChar(Canonical),@SA) then RaiseLastOSError;
 finally LocalFree(HLOCAL(SD));end;
 OutputDir:=Canonical;
end;
function Classification(const Text: string): string;
var L: string;
begin
 L:=LowerCase(Text);Result:='UNKNOWN';
 if Pos('not licensed',L)>0 then Result:='LICENSE_TOKEN'
 else if Pos('missing functional connection input',L)>0 then Result:='MISSING_INPUT'
 else if Pos('private disposable database acknowledgement required',L)>0 then Result:='PRIVATE_ACK_REQUIRED'
 else if (Pos('290',L)>0) and (Pos('driver',L)>0) then Result:='DRIVER_290_TOKEN'
 else if (Pos('im002',L)>0) or (Pos('data source name not found',L)>0) then Result:='DSN_NOT_FOUND_TOKEN'
 else if (Pos('driver',L)>0) and ((Pos('load',L)>0) or (Pos('not found',L)>0)) then Result:='DRIVER_LOAD_TOKEN'
 else if (Pos('authentication',L)>0) or (Pos('access denied',L)>0) then Result:='AUTH_TOKEN'
 else if (Pos('data source name',L)>0) or (Pos('dsn',L)>0) then Result:='DSN_TOKEN'
 else if Pos('odbc',L)>0 then Result:='ODBC_TOKEN';
end;
procedure EmitPresence;
var J: TJSONObject;
begin
 J:=TJSONObject.Create;
 try
  J.AddPair('event','environment_presence');
  J.AddPair('isolated_present',TJSONBool.Create(GetEnvironmentVariable('T2TI_MYSQL_ISOLATED')<>''));
  J.AddPair('isolated_yes',TJSONBool.Create(GetEnvironmentVariable('T2TI_MYSQL_ISOLATED')='YES'));
  J.AddPair('dsn_present',TJSONBool.Create(GetEnvironmentVariable('T2TI_MYSQL_DSN')<>''));
  J.AddPair('user_present',TJSONBool.Create(GetEnvironmentVariable('T2TI_MYSQL_USER')<>''));
  J.AddPair('password_present',TJSONBool.Create(GetEnvironmentVariable('T2TI_MYSQL_PASSWORD')<>''));
  Writeln(J.ToJSON);
 finally J.Free;end;
end;
procedure EmitError(E: Exception);
var J: TJSONObject; Bytes: TBytes; Saved: Boolean; MessageHash: THashSHA2;
begin
 Bytes:=TEncoding.UTF8.GetBytes(E.Message);Saved:=False;
 MessageHash:=THashSHA2.Create;MessageHash.Update(Bytes);
 if OutputDir<>'' then
  try TFile.WriteAllBytes(TPath.Combine(OutputDir,Stage+'-exception-private.utf8'),Bytes);Saved:=True;except end;
 J:=TJSONObject.Create;
 try
  J.AddPair('event','connection_failed');J.AddPair('stage',Stage);J.AddPair('sql_queries',TJSONNumber.Create(QueryCount));
  if Classification(E.Message)='LICENSE_TOKEN' then J.AddPair('native_gate','LICENSE_BLOCKED')
  else if Pos('BOUNDARY',Stage)>0 then J.AddPair('native_gate','SQL_BOUNDARY_FAILED')
  else J.AddPair('native_gate','LOADER_OR_CONNECTION_FAILED');
  J.AddPair('exception_class',E.ClassName);J.AddPair('classification',Classification(E.Message));
  J.AddPair('message_sha256',MessageHash.HashAsString);J.AddPair('message_bytes',TJSONNumber.Create(Length(Bytes)));
  J.AddPair('private_message_saved',TJSONBool.Create(Saved));
  if E is EOSError then J.AddPair('numeric_code',TJSONNumber.Create(EOSError(E).ErrorCode))
  else J.AddPair('numeric_code',TJSONNull.Create);
  Writeln(J.ToJSON);
 finally J.Free;end;
end;
procedure ProbeBoundary(const LiteralValue: string; Expected: Int64; InScope: Boolean);
var Q: TSQLQuery; J: TJSONObject; WideValue: Int64; NarrowValue: Integer;
    WideOK, NarrowOK: Boolean;
begin
 Q:=TSQLQuery.Create(nil);
 try
  Q.SQLConnection:=Connection.getConexao;
  Stage:='BOUNDARY_QUERY';Q.SQL.Text:='SELECT CAST('+LiteralValue+' AS UNSIGNED) AS probe_id';Inc(QueryCount);Q.Open;
  if Q.IsEmpty or Q.Fields[0].IsNull then raise Exception.Create('Boundary row missing');
  WideOK:=False;NarrowOK:=False;WideValue:=0;NarrowValue:=0;
  J:=TJSONObject.Create;
  try
   J.AddPair('event','boundary_observed');J.AddPair('expected',TJSONNumber.Create(Expected));
   J.AddPair('within_owned_signed_int32_scope',TJSONBool.Create(InScope));
   Stage:='BOUNDARY_WIDE_GETTER';
   try WideValue:=Q.Fields[0].AsLargeInt;WideOK:=True;
   except on E: Exception do EmitError(E);end;
   Stage:='BOUNDARY_INTEGER_GETTER';
   try NarrowValue:=Q.Fields[0].AsInteger;NarrowOK:=True;
   except on E: Exception do EmitError(E);end;
   J.AddPair('wide_getter_available',TJSONBool.Create(WideOK));
   J.AddPair('integer_getter_available',TJSONBool.Create(NarrowOK));
   if WideOK then J.AddPair('wide_value',TJSONNumber.Create(WideValue)) else J.AddPair('wide_value',TJSONNull.Create);
   if NarrowOK then J.AddPair('integer_value',TJSONNumber.Create(NarrowValue)) else J.AddPair('integer_value',TJSONNull.Create);
   J.AddPair('full_uint64_support','UNQUALIFIED');Writeln(J.ToJSON);
  finally J.Free;end;
  Stage:='BOUNDARY_VALIDATE';
  if InScope and (not WideOK or not NarrowOK or (WideValue<>Expected) or (Int64(NarrowValue)<>Expected)) then
   raise Exception.Create('Signed ID boundary mismatch');
  if not InScope then Writeln('{"event":"out_of_scope_observed","qualification":"NO_UINT64_PASS"}');
 finally Q.Free;end;
end;
begin
 Connection:=nil;Failed:=False;QueryCount:=0;OutputDir:='';Stage:='PRIVATE_OUTPUT';
 try
  PreparePrivateDirectory;EmitPresence;
  Stage:='CONNECTION_CREATE';Connection:=TOpenDriverConnection.Create;
  Stage:='CONNECTION_STATE';
  if not Connection.getConexao.Connected then raise Exception.Create('Connection not connected');
  if GetEnvironmentVariable('T2TI_OPEN_DBX_MODE')='ACTUAL_CONNECTION' then begin
   ProbeBoundary('0',0,True);ProbeBoundary('1',1,True);
   ProbeBoundary('2147483647',2147483647,True);ProbeBoundary('2147483648',2147483648,False);
  end else raise Exception.Create('Dummy DSN unexpectedly connected');
  Stage:='CONNECTION_FREE';FreeAndNil(Connection);
  Writeln('{"event":"connection_finished","native_gate":"CONNECTED_BOUNDARY_OBSERVED","connected_observed":true,"freed":true,"sql_queries":4,"full_uint64_support":"UNQUALIFIED"}');
 except on E: Exception do begin Failed:=True;EmitError(E);end;end;
 if Connection<>nil then
  try Connection.Free;except on E: Exception do begin Failed:=True;Stage:='CONNECTION_FINAL_FREE';EmitError(E);end;end;
 if Failed then Halt(1);
end.
