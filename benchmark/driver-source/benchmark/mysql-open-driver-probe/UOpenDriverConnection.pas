unit UOpenDriverConnection;
interface
uses System.SysUtils, Data.SqlExpr, Data.DBXCommon;
type TOpenDriverConnection = class
 private FConnection: TSQLConnection;
 public constructor Create;
 destructor Destroy; override;
 function getConexao: TSQLConnection;
end;
implementation
uses System.Classes, System.IOUtils, System.Hash, Dbx34Drv;
function RequiredEnv(const Name: string): string;
begin Result:=GetEnvironmentVariable(Name);if Result='' then raise Exception.Create('Missing functional connection input');end;
constructor TOpenDriverConnection.Create;
var Properties: TDBXOpenOdbcProperties; LibraryPath, Mode, Expected: string;
 Stream: TFileStream; Digest: THashSHA2; Buffer: TBytes; Count: Integer;
begin
 inherited Create;
 if SizeOf(Pointer)<>8 then raise Exception.Create('Win64 probe required');
 if RequiredEnv('T2TI_MYSQL_ISOLATED')<>'YES' then raise Exception.Create('Private disposable database acknowledgement required');
 LibraryPath:=TPath.GetFullPath(RequiredEnv('T2TI_OPEN_DBX_LIBRARY'));
 if not SameText(Copy(LibraryPath,1,16),'C:\build-inputs\') or not SameText(ExtractFileName(LibraryPath),'dbxoodbc.dll') then raise Exception.Create('Driver path binding invalid');
 Expected:=RequiredEnv('T2TI_OPEN_DBX_SHA256');
 if Length(Expected)<>64 then raise Exception.Create('Driver hash binding invalid');
 Stream:=TFileStream.Create(LibraryPath,fmOpenRead or fmShareDenyWrite);
 try
  Digest:=THashSHA2.Create;SetLength(Buffer,65536);
  repeat Count:=Stream.Read(Buffer[0],Length(Buffer));if Count>0 then begin SetLength(Buffer,Count);Digest.Update(Buffer);SetLength(Buffer,65536);end;until Count=0;
  if not SameText(Digest.HashAsString,Expected) then raise Exception.Create('Driver hash binding invalid');
 finally Stream.Free;end;
 Mode:=RequiredEnv('T2TI_OPEN_DBX_MODE');
 if (Mode<>'DUMMY_DSN') and (Mode<>'ACTUAL_CONNECTION') then raise Exception.Create('Probe mode binding invalid');
 FConnection:=TSQLConnection.Create(nil);
 try
  FConnection.LoginPrompt:=False;FConnection.DriverName:='DbxOpenOdbc';
  Properties:=TDBXOpenOdbcProperties.Create(nil);
  try FConnection.Params.Assign(Properties.Properties);finally Properties.Free;end;
  FConnection.LibraryName:=LibraryPath;FConnection.GetDriverFunc:='getSQLDriverODBCW';
  FConnection.VendorLib:='odbc32.dll';
  FConnection.Params.Values['LibraryName']:=LibraryPath;
  FConnection.Params.Values['GetDriverFunc']:='getSQLDriverODBCW';
  FConnection.Params.Values['VendorLib']:='odbc32.dll';
  if Mode='DUMMY_DSN' then begin
   FConnection.Params.Values['Database']:='T2TI_OPEN_DRIVER_UNREGISTERED_PROBE';
   FConnection.Params.Values['User_Name']:='';FConnection.Params.Values['Password']:='';
  end else begin
   FConnection.Params.Values['Database']:=RequiredEnv('T2TI_MYSQL_DSN');
   FConnection.Params.Values['User_Name']:=RequiredEnv('T2TI_MYSQL_USER');
   FConnection.Params.Values['Password']:=RequiredEnv('T2TI_MYSQL_PASSWORD');
  end;
  FConnection.KeepConnection:=True;FConnection.AutoClone:=False;FConnection.Connected:=True;
 except FConnection.Free;FConnection:=nil;raise;end;
end;
destructor TOpenDriverConnection.Destroy;
begin FConnection.Free;inherited;end;
function TOpenDriverConnection.getConexao: TSQLConnection;
begin Result:=FConnection;end;
end.
