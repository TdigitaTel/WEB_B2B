declare module 'qz-tray' {
  interface PrinterConfig {readonly printer: unknown}
  interface PrintOptions {
    units: 'in'; size: {width:number;height:number}; density:number; scaleContent:boolean;
    margins:number; orientation:'portrait'; colorType:'grayscale'; interpolation:'nearest-neighbor'; jobName:string;
  }
  interface QZ {
    websocket: {isActive():boolean;connect():Promise<void>};
    printers: {find():Promise<string[]>};
    configs: {create(name:string,options:PrintOptions):PrinterConfig};
    print(config:PrinterConfig,data:{type:'pixel';format:'pdf';flavor:'base64';data:string}[]):Promise<void>;
  }
  const qz: QZ;
  export default qz;
}
