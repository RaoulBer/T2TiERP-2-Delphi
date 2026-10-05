program SaleInquiryPerformance;
{$APPTYPE CONSOLE}
uses System.SysUtils, System.Classes, System.IOUtils, System.DateUtils,
 System.Diagnostics, System.JSON, System.Hash, System.Rtti, System.TypInfo,
 System.Generics.Collections, Winapi.Windows, Data.DB, Data.DBXCommon, Data.SqlExpr,
 UDataModuleConexaoDiagnosticV2b in '..\mysql-open-worker\generated-win32\UDataModuleConexaoDiagnosticV2b.pas',
 Atributos, Constantes, VO, T2TiORM, VendaCabecalhoVO, VendaDetalheVO, VendaComissaoVO;
type EQualification=class(Exception);
 TSaleRows<T:class>=class
 public class function Read(Prototype:TObject;const Filter:String):TObjectList<T>;static;end;
var Config:TJSONObject;RunId,Scenario,Attempt,WorkerId,Phase:String;
 H:TVendaCabecalhoVO;C:TVendaComissaoVO;D:TObjectList<TVendaDetalheVO>;
 Tx:TDBXTransaction;StartTick:Int64;OpenAttempt,Failed,OwnedCommitted:Boolean;
 CurrentHeaders,CurrentDetails,CurrentCommissions:TList<Integer>;Products:TArray<Integer>;
 CreationTime:TFileTime;CreationSystemTime:TSystemTime;ActualExeHash,InstanceId,SourceManifest,RollbackStatus:String;CurrentSteps:TList<String>;
 Ordinal:Int64;MinimumHeader,MinimumDetail,MinimumCommission,LastHeader,LastDetail,LastCommission:Integer;
 Deadline:TDateTime;
procedure Require(B:Boolean);begin if not B then raise EQualification.Create('SALE_ASSERTION');end;
function InputId(const Key:String):Integer;
begin Result:=Config.GetValue<Integer>(Key);Require(Result>0);end;
function RowsJSON(Obj:TObject):TJSONObject;
var Context:TRttiContext;P:TRttiProperty;A:TCustomAttribute;Name:String;V:TValue;
begin
 Result:=TJSONObject.Create;Context:=TRttiContext.Create;
 try
  for P in Context.GetType(Obj.ClassType).GetProperties do begin
   Name:='';for A in P.GetAttributes do begin
    if A is TId then Name:=TId(A).NameField;
    if (A is TColumn) and not TColumn(A).Transiente then Name:=TColumn(A).Name;
   end;
   if Name='' then Continue;V:=P.GetValue(Obj);
   case V.Kind of
    tkInteger:Result.AddPair(Name,TJSONNumber.Create(V.AsInteger));
    tkInt64:Result.AddPair(Name,TJSONNumber.Create(V.AsInt64));
    tkFloat:if P.PropertyType.Handle=TypeInfo(TDateTime) then begin
     if V.AsExtended=0 then Result.AddPair(Name,'ORIGINAL_VO_DATE_ZERO')
     else Result.AddPair(Name,FormatDateTime('yyyy-mm-dd',V.AsExtended));
    end else Result.AddPair(Name,FloatToStr(V.AsExtended,FormatSettings));
    tkString,tkLString,tkWString,tkUString:Result.AddPair(Name,V.AsString);
    else raise EQualification.Create('UNSUPPORTED_MAPPED_VALUE');
   end;
  end;
 finally Context.Free;end;
end;
function EqualVO(A,B:TObject):Boolean;
var Left,Right:TJSONObject;
begin Left:=nil;Right:=nil;try Left:=RowsJSON(A);Right:=RowsJSON(B);Result:=Left.ToJSON=Right.ToJSON;finally Left.Free;Right.Free;end;end;
function FileSHA(const Path:String):String;
var Stream:TFileStream;Buffer:TBytes;N:Integer;Hasher:THashSHA2;
begin
 Hasher:=THashSHA2.Create;Stream:=TFileStream.Create(Path,fmOpenRead or fmShareDenyWrite);
 try SetLength(Buffer,65536);repeat N:=Stream.Read(Buffer[0],Length(Buffer));if N>0 then begin SetLength(Buffer,N);Hasher.Update(Buffer);end;until N=0;finally Stream.Free;end;Result:=LowerCase(Hasher.HashAsString);
end;
function Identity:TJSONObject;
begin
 Result:=TJSONObject.Create;Result.AddPair('run_id',RunId);Result.AddPair('worker_id',TJSONNumber.Create(StrToInt(WorkerId)));
 Result.AddPair('pid',TJSONNumber.Create(GetCurrentProcessId));
 Result.AddPair('instance_id',InstanceId);
 Result.AddPair('creation_utc',Format('%.4d-%.2d-%.2dT%.2d:%.2d:%.2d.%.3dZ',[CreationSystemTime.wYear,CreationSystemTime.wMonth,CreationSystemTime.wDay,CreationSystemTime.wHour,CreationSystemTime.wMinute,CreationSystemTime.wSecond,CreationSystemTime.wMilliseconds]));
 Result.AddPair('creation_filetime_low',TJSONNumber.Create(Int64(CreationTime.dwLowDateTime)));Result.AddPair('creation_filetime_high',TJSONNumber.Create(Int64(CreationTime.dwHighDateTime)));
 Result.AddPair('exe_sha256',ActualExeHash);
 Result.AddPair('driver_sha256',GetEnvironmentVariable('T2TI_OPEN_DBX_SHA256'));
 Result.AddPair('source_manifest_sha256',SourceManifest);
end;
function IDs(L:TList<Integer>):TJSONArray;
var I:Integer;begin Result:=TJSONArray.Create;for I in L do Result.Add(I);end;
procedure Emit(const Kind,Outcome:String;Fields:TJSONObject=nil);
var E,L:TJSONObject;Steps:TJSONArray;Tick:Int64;I:Integer;
begin
 E:=TJSONObject.Create;
 try
  Tick:=TStopwatch.GetTimeStamp;E.AddPair('event',Kind);E.AddPair('operation',Scenario);E.AddPair('attempt_id',Attempt);E.AddPair('global_attempt_id',Attempt);E.AddPair('phase',Phase);E.AddPair('identity',Identity);
  E.AddPair('outcome',Outcome);E.AddPair('qpc_tick',TJSONNumber.Create(Tick));E.AddPair('qpc_frequency',TJSONNumber.Create(TStopwatch.Frequency));E.AddPair('observed_utc',DateToISO8601(TTimeZone.Local.ToUniversalTime(Now),True));
  if Kind='attempt_terminal' then begin E.AddPair('start_qpc_tick',TJSONNumber.Create(StartTick));E.AddPair('duration_qpc_ticks',TJSONNumber.Create(Tick-StartTick));E.AddPair('retries',TJSONNumber.Create(0));E.AddPair('rollback_status',RollbackStatus);Steps:=TJSONArray.Create;for I:=0 to CurrentSteps.Count-1 do Steps.Add(CurrentSteps[I]);E.AddPair('business_steps',Steps);end;
  L:=TJSONObject.Create;L.AddPair('VENDA_CABECALHO',IDs(CurrentHeaders));L.AddPair('VENDA_DETALHE',IDs(CurrentDetails));L.AddPair('VENDA_COMISSAO',IDs(CurrentCommissions));E.AddPair('claimed_owned_ids_require_independent_observation',L);
  if Fields<>nil then E.AddPair('fields',Fields);WriteLn(E.ToJSON);Flush(Output);
 finally E.Free;end;
end;
procedure Step(const Name:String);begin CurrentSteps.Add(Name);end;
procedure StartAttempt;
begin Require(not OpenAttempt);CurrentSteps.Clear;RollbackStatus:='NOT_REQUIRED';StartTick:=TStopwatch.GetTimeStamp;OpenAttempt:=True;Emit('attempt_started','PENDING');end;
procedure FinishAttempt;
begin Require(OpenAttempt and (Tx=nil));Emit('attempt_terminal','COMPLETED_PENDING_INDEPENDENT_OBSERVER');OpenAttempt:=False;end;
procedure BeginTx;begin Require(Tx=nil);Tx:=FDataModuleConexao.getConexao.BeginTransaction(TDBXIsolations.ReadCommitted);end;
procedure CommitTx;begin FDataModuleConexao.getConexao.CommitFreeAndNil(Tx);if OpenAttempt then Step('COMMIT');end;
procedure RollbackTx;begin if Tx<>nil then begin RollbackStatus:='PENDING';FDataModuleConexao.getConexao.RollbackFreeAndNil(Tx);RollbackStatus:='ROLLED_BACK';if OpenAttempt then Step('ROLLBACK');end;end;
procedure CaptureId(Id,Minimum:Integer;var Last:Integer;Current:TList<Integer>);
begin Require((Id>Minimum) and (Id>Last) and (Id>0));Last:=Id;Current.Add(Id);Emit('generated_id','ORM_LAST_INSERT_ID_REQUIRES_INDEPENDENT_OBSERVATION');end;
class function TSaleRows<T>.Read(Prototype:TObject;const Filter:String):TObjectList<T>;
var R:TDBXReader;Cmd:TDBXCommand;
begin
 Result:=TObjectList<T>.Create;R:=nil;Cmd:=nil;
 try
  try R:=TT2TiORM.Consultar(Prototype,Filter,'-1',Cmd);while R.Next do Result.Add(TGenericVO<T>.FromDBXReader(R));
  finally try R.Free;finally Cmd.Free;end;end;
 except Result.Free;raise;end;
end;
procedure Snapshot(Absent:Boolean);
var HR:TObjectList<TVendaCabecalhoVO>;DR:TObjectList<TVendaDetalheVO>;CR:TObjectList<TVendaComissaoVO>;
 HP:TVendaCabecalhoVO;DP:TVendaDetalheVO;CP:TVendaComissaoVO;I,J:Integer;Found:Boolean;Fields:TJSONObject;A:TJSONArray;
begin
 BeginTx;HR:=nil;DR:=nil;CR:=nil;HP:=TVendaCabecalhoVO.Create;DP:=TVendaDetalheVO.Create;CP:=TVendaComissaoVO.Create;
 try
  try
   HR:=TSaleRows<TVendaCabecalhoVO>.Read(HP,'ID = '+IntToStr(H.Id));Step('READ_HEADER_ORIGINAL_VO');
   DR:=TSaleRows<TVendaDetalheVO>.Read(DP,'ID_VENDA_CABECALHO = '+IntToStr(H.Id));Step('READ_OWN_DETAILS_ORIGINAL_VO');
   CR:=TSaleRows<TVendaComissaoVO>.Read(CP,'ID_VENDA_CABECALHO = '+IntToStr(H.Id));Step('READ_OWN_COMMISSION_ORIGINAL_VO');
   if Absent then Require((HR.Count=0) and (DR.Count=0) and (CR.Count=0)) else begin
    Require((HR.Count=1) and (DR.Count=D.Count) and (CR.Count=1));
    Fields:=RowsJSON(HR[0]);try Require(Fields.Count=26);finally Fields.Free;end;
    Fields:=RowsJSON(CR[0]);try Require(Fields.Count=8);finally Fields.Free;end;
    Require(EqualVO(HR[0],H));Require(EqualVO(CR[0],C));
    for I:=0 to D.Count-1 do begin
     Found:=False;for J:=0 to DR.Count-1 do if DR[J].Id=D[I].Id then begin
      Require(not Found);Found:=True;Fields:=RowsJSON(DR[J]);try Require((Fields.Count=11) and EqualVO(DR[J],D[I]));finally Fields.Free;end;
     end;Require(Found);
    end;
   end;
   Fields:=TJSONObject.Create;A:=TJSONArray.Create;for I:=0 to HR.Count-1 do A.AddElement(RowsJSON(HR[I]));Fields.AddPair('VENDA_CABECALHO',A);
   A:=TJSONArray.Create;for I:=0 to DR.Count-1 do A.AddElement(RowsJSON(DR[I]));Fields.AddPair('VENDA_DETALHE',A);
   A:=TJSONArray.Create;for I:=0 to CR.Count-1 do A.AddElement(RowsJSON(CR[I]));Fields.AddPair('VENDA_COMISSAO',A);
   Emit('original_vo_read','SHALLOW_VALUES_NULL_MAPPING_LOSS_DISCLOSED',Fields);CommitTx;
  except RollbackTx;raise;end;
 finally HR.Free;DR.Free;CR.Free;HP.Free;DP.Free;CP.Free;end;
end;
procedure PrepareSale;
var I:Integer;Line:TVendaDetalheVO;
begin
 CurrentHeaders.Clear;CurrentDetails.Clear;CurrentCommissions.Clear;
 H.Free;C.Free;H:=TVendaCabecalhoVO.Create;C:=TVendaComissaoVO.Create;D.Clear;
 H.IdCliente:=InputId('customer_id');H.IdVendedor:=InputId('seller_id');H.IdTipoNotaFiscal:=InputId('invoice_type_id');
 H.IdVendaCondicoesPagamento:=InputId('payment_terms_id');H.IdTransportadora:=InputId('transporter_id');
 H.DataVenda:=EncodeDate(2026,1,1);H.DataSaida:=EncodeDate(2026,1,2);H.LocalEntrega:='SYNTHETIC DELIVERY';H.LocalCobranca:='SYNTHETIC COLLECTION';
 H.TipoFrete:='C';H.FormaPagamento:='0';H.Situacao:='D';H.Observacao:='OWNED CREATED';H.TaxaComissao:=10;H.ValorSubtotal:=150;H.ValorTotal:=150;H.ValorComissao:=15;
 C.IdVendedor:=H.IdVendedor;C.ValorVenda:=150;C.ValorComissao:=15;C.DataLancamento:=H.DataVenda;C.TipoContabil:='C';C.Situacao:='A';
 for I:=0 to 4 do begin Line:=TVendaDetalheVO.Create;D.Add(Line);Line.IdProduto:=Products[I];Line.Quantidade:=I+1;Line.ValorUnitario:=10;Line.ValorSubtotal:=(I+1)*10;Line.ValorTotal:=Line.ValorSubtotal;Line.TaxaComissao:=10;Line.ValorComissao:=I+1;end;
end;
procedure InsertSale;
var I:Integer;
begin
 BeginTx;
 try
  H.Id:=TT2TiORM.Inserir(H);CaptureId(H.Id,MinimumHeader,LastHeader,CurrentHeaders);Step('INSERT_HEADER');
  C.IdVendaCabecalho:=H.Id;C.Id:=TT2TiORM.Inserir(C);CaptureId(C.Id,MinimumCommission,LastCommission,CurrentCommissions);Step('INSERT_COMMISSION');
  for I:=0 to 4 do begin D[I].IdVendaCabecalho:=H.Id;D[I].Id:=TT2TiORM.Inserir(D[I]);CaptureId(D[I].Id,MinimumDetail,LastDetail,CurrentDetails);end;
  Step('INSERT_FIVE_DETAILS');CommitTx;OwnedCommitted:=True;
 except RollbackTx;raise;end;
end;
procedure ChangeSale;
var Line:TVendaDetalheVO;
begin
 BeginTx;
 try
  H.Observacao:='OWNED UPDATED';H.ValorSubtotal:=220;H.ValorTotal:=220;H.ValorComissao:=22;Require(TT2TiORM.Alterar(H));Step('UPDATE_HEADER');
  C.ValorVenda:=220;C.ValorComissao:=22;Require(TT2TiORM.Alterar(C));Step('UPDATE_OWN_COMMISSION');
  D[0].Quantidade:=2;D[0].ValorSubtotal:=20;D[0].ValorTotal:=20;D[0].ValorComissao:=2;Require(TT2TiORM.Alterar(D[0]));Step('UPDATE_OWN_DETAIL');
  Line:=TVendaDetalheVO.Create;D.Add(Line);Line.IdProduto:=Products[0];Line.IdVendaCabecalho:=H.Id;Line.Quantidade:=6;Line.ValorUnitario:=10;Line.ValorSubtotal:=60;Line.ValorTotal:=60;Line.TaxaComissao:=10;Line.ValorComissao:=6;
  Line.Id:=TT2TiORM.Inserir(Line);CaptureId(Line.Id,MinimumDetail,LastDetail,CurrentDetails);Step('INSERT_OWN_DETAIL');CommitTx;
 except RollbackTx;raise;end;
end;
procedure CompensatedDelete;
var I:Integer;
begin
 Require(OwnedCommitted);BeginTx;
 try
  Require(CurrentHeaders.Contains(H.Id) and CurrentCommissions.Contains(C.Id));
  for I:=0 to D.Count-1 do begin Require(CurrentDetails.Contains(D[I].Id));Require(TT2TiORM.Excluir(D[I]));end;
  Step('EXCLUIR_OWN_DETAILS');Require(TT2TiORM.Excluir(C));Step('EXCLUIR_OWN_COMMISSION');Require(TT2TiORM.Excluir(H));Step('EXCLUIR_OWN_HEADER');CommitTx;OwnedCommitted:=False;
 except RollbackTx;raise;end;
end;
procedure ReadExistingSale;
var HP:TVendaCabecalhoVO;DP:TVendaDetalheVO;CP:TVendaComissaoVO;
 HR:TObjectList<TVendaCabecalhoVO>;DR:TObjectList<TVendaDetalheVO>;CR:TObjectList<TVendaComissaoVO>;
 Key:Int64;I:Integer;Fields:TJSONObject;Rows:TJSONArray;
begin
 Key:=1+((Ordinal-1)*9973+StrToInt(WorkerId)*307) mod MinimumHeader;
 CurrentHeaders.Clear;CurrentDetails.Clear;CurrentCommissions.Clear;
 HP:=TVendaCabecalhoVO.Create;DP:=TVendaDetalheVO.Create;CP:=TVendaComissaoVO.Create;HR:=nil;DR:=nil;CR:=nil;
 BeginTx;
 try
  try
   HR:=TSaleRows<TVendaCabecalhoVO>.Read(HP,'ID = '+IntToStr(Key));Step('READ_EXISTING_HEADER_ORIGINAL_VO');
   DR:=TSaleRows<TVendaDetalheVO>.Read(DP,'ID_VENDA_CABECALHO = '+IntToStr(Key));Step('READ_EXISTING_DETAILS_ORIGINAL_VO');
   CR:=TSaleRows<TVendaComissaoVO>.Read(CP,'ID_VENDA_CABECALHO = '+IntToStr(Key));Step('READ_EXISTING_COMMISSION_ORIGINAL_VO');
   Require((HR.Count=1) and (DR.Count=5) and (CR.Count=1) and (HR[0].Id=Key) and (CR[0].IdVendaCabecalho=Key));
   for I:=0 to DR.Count-1 do Require((DR[I].IdVendaCabecalho=Key) and (DR[I].IdProduto>0));
   Fields:=TJSONObject.Create;Rows:=TJSONArray.Create;for I:=0 to HR.Count-1 do Rows.AddElement(RowsJSON(HR[I]));Fields.AddPair('VENDA_CABECALHO',Rows);
   Rows:=TJSONArray.Create;for I:=0 to DR.Count-1 do Rows.AddElement(RowsJSON(DR[I]));Fields.AddPair('VENDA_DETALHE',Rows);
   Rows:=TJSONArray.Create;for I:=0 to CR.Count-1 do Rows.AddElement(RowsJSON(CR[I]));Fields.AddPair('VENDA_COMISSAO',Rows);
   Emit('existing_original_vo_read','PENDING_INDEPENDENT_DATASET_VALUE_VERIFICATION',Fields);CommitTx;
  except RollbackTx;raise;end;
 finally HR.Free;DR.Free;CR.Free;HP.Free;DP.Free;CP.Free;end;
end;
procedure ExecuteOne;
begin
 Require(TTimeZone.Local.ToUniversalTime(Now)<Deadline);Inc(Ordinal);Attempt:=RunId+':'+WorkerId+':'+Scenario+':'+IntToStr(Ordinal);
 if Scenario='SALE_READ' then begin StartAttempt;ReadExistingSale;FinishAttempt;Exit;end;
 Emit('setup_started','OUTSIDE_OPERATION_TIMER');PrepareSale;
 if Scenario<>'SALE_CREATE' then InsertSale;
 Emit('setup_terminal','COMPLETED_OUTSIDE_OPERATION_TIMER');StartAttempt;
 if Scenario='SALE_CREATE' then InsertSale
 else if Scenario='SALE_READ' then Snapshot(False)
 else if Scenario='SALE_UPDATE' then ChangeSale
 else if Scenario='SALE_DELETE' then CompensatedDelete
 else raise EQualification.Create('OPERATION_INVALID');
 FinishAttempt;
 Emit('cleanup_started','OUTSIDE_OPERATION_TIMER');if OwnedCommitted then CompensatedDelete;Emit('cleanup_terminal','OWNED_DELETE_COMPLETED_PENDING_INDEPENDENT_ABSENCE');
end;
procedure RepeatPhase(const Name:String;Seconds:Integer);
var Clock:TStopwatch;
begin
 Phase:=Name;Clock:=TStopwatch.StartNew;Emit('phase_started','SINGLE_OPERATION_CELL');
 while Clock.Elapsed.TotalSeconds<Seconds do begin
  Require(Ordinal<Config.GetValue<Int64>('maximum_attempts'));ExecuteOne;
 end;
 Emit('phase_terminal','ELAPSED_TARGET_NO_LATENCY_AGGREGATION');
end;
var Value:TJSONValue;A:TJSONArray;I:Integer;ExitTime,KernelTime,UserTime:TFileTime;Proof,Fatal:TJSONObject;ErrorBytes:TBytes;ErrorHash:THashSHA2;
begin
 Config:=nil;H:=nil;C:=nil;D:=TObjectList<TVendaDetalheVO>.Create;CurrentHeaders:=TList<Integer>.Create;CurrentDetails:=TList<Integer>.Create;CurrentCommissions:=TList<Integer>.Create;CurrentSteps:=TList<String>.Create;Tx:=nil;Failed:=False;OpenAttempt:=False;OwnedCommitted:=False;Ordinal:=0;WorkerId:='0';
 try
  try
   FormatSettings.DecimalSeparator:='.';Require(GetProcessTimes(GetCurrentProcess,CreationTime,ExitTime,KernelTime,UserTime));Require(FileTimeToSystemTime(CreationTime,CreationSystemTime));ActualExeHash:=FileSHA(ParamStr(0));Require(ParamCount=2);RunId:=ParamStr(1);Require(Length(RunId)=32);
   for I:=1 to Length(RunId) do Require(CharInSet(RunId[I],['a'..'f','0'..'9']));
   Value:=TJSONObject.ParseJSONValue(TFile.ReadAllText(ParamStr(2)));Require(Value is TJSONObject);Config:=TJSONObject(Value);
   Require(Config.GetValue<String>('exe_sha256')=ActualExeHash);Require(Config.GetValue<String>('run_id')=RunId);WorkerId:=IntToStr(Config.GetValue<Integer>('worker_id'));Require(StrToInt(WorkerId)>=0);
   InstanceId:=Config.GetValue<String>('instance_id');SourceManifest:=Config.GetValue<String>('source_manifest_sha256');Require((Length(InstanceId)>0) and (Length(SourceManifest)=64));
   for I:=1 to Length(InstanceId) do Require(CharInSet(InstanceId[I],['0'..'9']));for I:=1 to Length(SourceManifest) do Require(CharInSet(SourceManifest[I],['a'..'f','0'..'9']));
   Require(Config.GetValue<String>('database')=GetEnvironmentVariable('T2TI_MYSQL_DATABASE'));Require((SizeOf(Pointer)=4) and (GetEnvironmentVariable('T2TI_MYSQL_FUNCTIONAL')='YES'));
   Require(Config.GetValue<String>('sale_contract_sha256')='2775e3fbcefcb324d4c529c625bb04d44da2434bf4ed7e5988676157c12847e3');
   Require(Length(Config.GetValue<String>('functional_receipt_sha256'))=64);Require(FileSHA(Config.GetValue<String>('functional_receipt_path'))=Config.GetValue<String>('functional_receipt_sha256'));
   Proof:=TJSONObject.ParseJSONValue(TFile.ReadAllText(Config.GetValue<String>('functional_receipt_path'))) as TJSONObject;
   try Require((Proof.GetValue<String>('status')='GENUINE_SALE_SIX_SCENARIOS_40_BASELINE_QUALIFIED') and Proof.GetValue<Boolean>('native_qualification') and Proof.GetValue<Boolean>('cleanup'));finally Proof.Free;end;
   Deadline:=ISO8601ToDate(Config.GetValue<String>('deadline_utc'),True);Require(TTimeZone.Local.ToUniversalTime(Now)+300/SecsPerDay<Deadline);
   Scenario:=Config.GetValue<String>('operation');Require((Scenario='SALE_CREATE') or (Scenario='SALE_READ') or (Scenario='SALE_UPDATE') or (Scenario='SALE_DELETE'));
   Require(Config.GetValue<Int64>('maximum_attempts')>0);MinimumHeader:=InputId('baseline_header_max_id');MinimumDetail:=InputId('baseline_detail_max_id');MinimumCommission:=InputId('baseline_commission_max_id');LastHeader:=MinimumHeader;LastDetail:=MinimumDetail;LastCommission:=MinimumCommission;
   A:=Config.GetValue<TJSONArray>('product_ids');Require(A.Count=5);SetLength(Products,5);for I:=0 to 4 do begin Products[I]:=A.Items[I].GetValue<Integer>;Require(Products[I]>0);end;
   FDataModuleConexao:=TFDataModuleConexao.Create;
   RepeatPhase('WARMUP',60);RepeatPhase('MEASUREMENT',180);RepeatPhase('COOLDOWN',30);Emit('worker_finished','PENDING_INDEPENDENT_BASELINE_AND_OWNERSHIP_REVIEW');
  except on E:Exception do begin
   Failed:=True;ErrorBytes:=TEncoding.UTF8.GetBytes(E.Message);ErrorHash:=THashSHA2.Create;ErrorHash.Update(ErrorBytes);Fatal:=TJSONObject.Create;Fatal.AddPair('exception_class',E.ClassName);Fatal.AddPair('message_sha256',LowerCase(ErrorHash.HashAsString));Fatal.AddPair('message_bytes',TJSONNumber.Create(Length(ErrorBytes)));Emit('native_error','UNCLASSIFIED_NO_RAW_MESSAGE',Fatal);try RollbackTx;except RollbackStatus:='UNRESOLVED';end;
   if OpenAttempt then begin Emit('attempt_terminal','FAILED');OpenAttempt:=False;end;
   Emit('worker_fatal','INCOMPLETE_NO_RAW_ERROR');
   try if OwnedCommitted and (Tx=nil) then begin Emit('cleanup_started','FAILURE_CLEANUP_OUTSIDE_TIMER');CompensatedDelete;Emit('cleanup_terminal','PENDING_INDEPENDENT_ABSENCE');end;except Emit('cleanup_terminal','UNRESOLVED_PARENT_OWNED_RESIDUAL_RECONCILIATION_REQUIRED');end;
  end;end;
 finally FDataModuleConexao.Free;FDataModuleConexao:=nil;Config.Free;H.Free;C.Free;D.Free;CurrentHeaders.Free;CurrentDetails.Free;CurrentCommissions.Free;CurrentSteps.Free;end;
 if Failed then Halt(1);
end.
