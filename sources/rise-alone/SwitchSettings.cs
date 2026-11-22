using System;
using System.IO;
using System.Text;

namespace RiseAlone
{
    public sealed class SwitchSettings
    {
        private readonly string path;
        public bool Energy {get;private set;}
        public bool Favor {get;private set;}
        public bool Pressure {get;private set;}
        public bool MiniGames {get;private set;}
        public bool ChoiceGuard {get;private set;}
        public bool MapLabels {get;private set;}
        public bool UnlimitedChoiceTime {get;private set;}
        public SwitchSettings(string path){this.path=path;}
        public void Load()
        {
            if(!File.Exists(path))return;
            string text=File.ReadAllText(path).Trim();
            bool legacy=text.Length==4 && text.StartsWith("1:",StringComparison.Ordinal);
            bool current=text.Length==5 && text.StartsWith("2:",StringComparison.Ordinal);
            bool withMini=text.Length==6 && text.StartsWith("3:",StringComparison.Ordinal);
            bool withGuard=text.Length==8 && text.StartsWith("4:",StringComparison.Ordinal);
            bool withTimer=text.Length==9 && text.StartsWith("5:",StringComparison.Ordinal);
            if(!legacy && !current && !withMini && !withGuard && !withTimer)
                throw new InvalidDataException("开关配置无效，本次以关闭状态启动。");
            for(int i=2;i<text.Length;i++)
                if(text[i]!='0' && text[i]!='1')throw new InvalidDataException("开关配置包含无效值。");
            Energy=text[2]=='1';Favor=text[3]=='1';
            Pressure=!legacy && text[4]=='1';
            MiniGames=(withMini || withGuard || withTimer) && text[5]=='1';
            ChoiceGuard=(withGuard || withTimer) && text[6]=='1';
            MapLabels=(withGuard || withTimer) && text[7]=='1';
            UnlimitedChoiceTime=withTimer && text[8]=='1';
        }
        public void Save(bool energy,bool favor,bool pressure,bool miniGames=false,bool choiceGuard=false,bool mapLabels=false,bool unlimitedChoiceTime=false)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            string temp=path+"."+Guid.NewGuid().ToString("N")+".tmp";
            try{
                byte[] payload=Encoding.ASCII.GetBytes("5:"+(energy?"1":"0")+(favor?"1":"0")+(pressure?"1":"0")+(miniGames?"1":"0")+(choiceGuard?"1":"0")+(mapLabels?"1":"0")+(unlimitedChoiceTime?"1":"0"));
                using(var file=new FileStream(temp,FileMode.CreateNew,FileAccess.Write,FileShare.None)){
                    file.Write(payload,0,payload.Length);file.Flush(true);
                }
                File.Move(temp,path,true);
                Energy=energy;Favor=favor;Pressure=pressure;MiniGames=miniGames;ChoiceGuard=choiceGuard;MapLabels=mapLabels;
                UnlimitedChoiceTime=unlimitedChoiceTime;
            }finally{if(File.Exists(temp))File.Delete(temp);}
        }
    }
}
