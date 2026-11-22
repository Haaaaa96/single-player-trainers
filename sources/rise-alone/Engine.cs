using System;
using System.Globalization;

namespace RiseAlone
{
    public interface ISlot
    {
        string Identity { get; }
        string LoadedSlot { get; }
        bool FirstMorningHomePending { get; }
        string CombatTurn { get; }
        void RefreshCombatPoints();
        long Base(string key);
        long Effective(string key);
        void Set(string key, long value);
        void Backup();
    }

    public sealed class Reading
    {
        public Entry Item;
        public string Session;
        public string CombatTurn;
        public long Base, Effective, Max;
    }

    public sealed class Engine
    {
        public bool NoEnergyLoss { get; private set; }
        public bool EnergyAvailable=true;
        public bool CheckEnergy {get{return EnergyAvailable && (NoEnergyLoss || settings.Energy);}}
        public bool FullFavor { get; private set; }
        public bool AutoMiniGames { get; private set; }
        public bool MiniGameAvailable=true;
        public bool ChoiceAvailable=true;
        public bool ChoiceGuard {get;private set;}
        public bool MapLabels {get;private set;}
        public bool ChoiceTimerAvailable=true;
        public bool UnlimitedChoiceTime {get;private set;}
        public bool CheckChoiceTimer {get{return ChoiceTimerAvailable && (UnlimitedChoiceTime || (identity==null && settings.UnlimitedChoiceTime));}}
        public bool CheckChoices {get{return ChoiceAvailable && (ChoiceGuard || (identity==null && settings.ChoiceGuard));}}
        public bool CheckMiniGames {get{return AutoMiniGames || (identity==null && MiniGameAvailable && settings.MiniGames);}}
        public bool ZeroPressure { get; private set; }
        public bool PressureAvailable=true;
        public bool CheckPressure {get{return PressureAvailable && (ZeroPressure || settings.Pressure);}}
        public string Last = "";
        public string Session { get; private set; } = "";
        private string identity;
        private string loadedSlot;
        private readonly SwitchSettings settings;
        public bool FavorAvailable=true;
        public bool CheckFavor {get{return FullFavor || (identity==null && FavorAvailable && settings.Favor);}}
        public bool Watch {get{return CheckEnergy || FullFavor || settings.Favor || CheckPressure || AutoMiniGames || settings.MiniGames || ChoiceGuard || settings.ChoiceGuard || MapLabels || settings.MapLabels || CheckChoiceTimer;}}
        public Engine(SwitchSettings settings){this.settings=settings;}

        public string RentalHint(ISlot slot)
        {
            if(slot==null || !slot.FirstMorningHomePending)return "";
            if(slot.Effective("Execution")<4)
                return "行动力已达标。重新进入地图后，前往出租屋触发回家剧情。";
            if(NoEnergyLoss)
                return "首日回出租屋需要行动力低于 4。开着「行动力不减少」也能手动把行动力设为 3。";
            return "首日回出租屋需要行动力低于 4。可以正常消耗，也可以在主角页把行动力设为 3。";
        }
        private bool protectedSlot;
        private bool writing;
        private long? requestedEnergy;
        private string requestedSession;
        internal void RebindAfterReselect(ISlot slot){
            if(slot==null)return;
            identity=slot.Identity;
            loadedSlot=slot.LoadedSlot;
            Session=Guid.NewGuid().ToString("N");
            protectedSlot=false;
        }

        public void Observe(ISlot slot)
        {
            string next = slot == null ? null : slot.Identity;
            if(next == identity) return;
            bool sameData=slot!=null && loadedSlot==slot.LoadedSlot;
            loadedSlot=slot?.LoadedSlot;
            identity = next;
            Session = next == null ? "" : Guid.NewGuid().ToString("N");
            protectedSlot=false;
            if(sameData)return;
            NoEnergyLoss=slot!=null && settings.Energy && EnergyAvailable;
            FullFavor=slot!=null && settings.Favor && FavorAvailable;
            AutoMiniGames=slot!=null && settings.MiniGames && MiniGameAvailable;
            ChoiceGuard=slot!=null && settings.ChoiceGuard && ChoiceAvailable;
            MapLabels=slot!=null && settings.MapLabels;
            UnlimitedChoiceTime=slot!=null && ChoiceTimerAvailable && settings.UnlimitedChoiceTime;
            ZeroPressure=slot!=null && settings.Pressure && PressureAvailable;
            Last = "";
        }

        public Reading Read(ISlot slot,Entry entry)
        {
            Observe(slot);
            if(slot==null)return null;
            var reading=new Reading{Item=entry,Session=Session};
            if(entry.Key==Catalog.FightPoints){
                reading.CombatTurn=slot.CombatTurn;
                if(String.IsNullOrEmpty(reading.CombatTurn))return reading;
            }
            reading.Base=slot.Base(entry.Key);
            reading.Effective=slot.Effective(entry.Key);
            reading.Max=entry.Key=="Execution"?EnergyCap(slot):entry.Full;
            return reading;
        }

        private void Require(ISlot slot,Reading previous)
        {
            Observe(slot);
            if(slot==null || previous==null || previous.Session!=Session)throw new InvalidOperationException("存档已切换，请重新选择。");
        }
        public void SetNumber(ISlot slot,Reading previous,string input)
        {
            Require(slot,previous);
            Entry entry=previous.Item;
            if(entry.Key==Catalog.FightPoints && (String.IsNullOrEmpty(previous.CombatTurn) || slot.CombatTurn!=previous.CombatTurn))
                throw new InvalidOperationException("请在当前战斗的选招界面设置本场战技点。");
            if(slot.Base(entry.Key)!=previous.Base || slot.Effective(entry.Key)!=previous.Effective)
                throw new InvalidOperationException("当前值刚有变化，请核对后再设置。");
            if(ZeroPressure && entry.Key=="Pressure") throw new InvalidOperationException("请先关闭保持零压力。");
            long value=Parse(input);
            long min=entry.Key=="Morality" || entry.Key==Catalog.ZhaoApproval?-999999:0;
            long max=Catalog.Limit(entry,entry.Key=="Execution"?EnergyCap(slot):0);
            if(value<min || value>max)throw new ArgumentException("可设范围为 "+min+" 至 "+max+"。");
            if(entry.Key=="Execution" || entry.Key==Catalog.FightPoints || entry.Key==Catalog.OpeningPoints)SetEffective(slot,entry.Key,value);
            else Write(slot,entry.Key,value);
            Last=entry.Name+"已设为 "+value;
            if(entry.Key==Catalog.FightPoints){
                try{slot.RefreshCombatPoints();}
                catch(Exception){Last+="，点数已读回，图标将在下次选招时刷新。";}
            }
        }
        public void SetEnergy(ISlot slot,Reading previous,bool enable)
        {
            Require(slot,previous);
            if(enable && !EnergyAvailable)throw new InvalidOperationException("当前版本的行动力结算入口未加载。");
            NoEnergyLoss=enable;Last=enable?"行动力不减少已开启":"行动力不减少已关闭";
        }
        public void SetFavor(ISlot slot,Reading previous,bool enable)
        {
            Require(slot,previous);
            if(enable && !FavorAvailable)throw new InvalidOperationException("人物交互入口未加载。");
            FullFavor=enable;Last=enable?"交互人物满好感已开启":"交互人物满好感已关闭";
        }
        public void SaveSettings(ISlot slot,Reading previous)
        {
            Require(slot,previous);
            settings.Save(EnergyAvailable?NoEnergyLoss:settings.Energy,FullFavor,PressureAvailable?ZeroPressure:settings.Pressure,
                MiniGameAvailable?AutoMiniGames:settings.MiniGames,ChoiceAvailable?ChoiceGuard:settings.ChoiceGuard,MapLabels,
                ChoiceTimerAvailable?UnlimitedChoiceTime:settings.UnlimitedChoiceTime);
            Last="设置已保存，重启游戏和换档后生效。";
        }

        public void SetMiniGames(ISlot slot,Reading previous,bool enable)
        {
            Require(slot,previous);
            if(enable && !MiniGameAvailable)throw new InvalidOperationException("当前版本的小游戏操作入口未加载。");
            AutoMiniGames=enable;
            Last=enable?"小游戏自动完成已开启":"小游戏自动完成已关闭";
        }
        public void SetChoiceGuard(ISlot slot,Reading previous,bool enable)
        {
            Require(slot,previous);
            if(enable && !ChoiceAvailable)throw new InvalidOperationException("任务选择入口未加载。");
            ChoiceGuard=enable;
            Last=enable?"任务防误选已开启":"任务防误选已关闭";
        }
        public void SetMapLabels(ISlot slot,Reading previous,bool enable){
            Require(slot,previous);MapLabels=enable;
            Last=enable?"地图将标出当前能进入的未解锁地点":"已关闭未解锁地点标记";
        }
        public void SetUnlimitedChoiceTime(ISlot slot,Reading previous,bool enable){
            Require(slot,previous);
            if(enable && !ChoiceTimerAvailable)throw new InvalidOperationException("当前版本的限时选项入口未加载。");
            UnlimitedChoiceTime=enable;
            Last=enable?"限时选项会等到你手动选择。":"已恢复游戏原有的选择时限。";
        }
        public bool PrepareMiniGame(ISlot slot)
        {
            Observe(slot);
            if(slot==null || !AutoMiniGames || writing)return false;
            Protect(slot);
            return true;
        }
        public void StopMiniGame(Exception error)
        {
            AutoMiniGames=false;
            Last="小游戏自动完成已停止："+error.GetBaseException().Message;
        }

        public void SetZeroPressure(ISlot slot,Reading previous,bool enable)
        {
            Require(slot,previous);
            if(enable && !PressureAvailable)throw new InvalidOperationException("当前版本的压力读写入口未加载。");
            ZeroPressure=enable;
            try {if(enable)Write(slot,"Pressure",0);}
            catch {ZeroPressure=false;throw;}
            Last=enable?"保持零压力已开启":"保持零压力已关闭";
        }

        public long PressureReading(ISlot slot,long gameValue)
        {
            Observe(slot);
            return ZeroPressure?0:gameValue;
        }

        public void BeforePressureChange(ISlot slot,ref long amount,bool additive)
        {
            Observe(slot);
            if(!ZeroPressure)return;
            long adjusted=additive?checked(-slot.Base("Pressure")):0;
            if(adjusted==amount)return;
            Protect(slot);
            amount=adjusted;
        }

        public void StopPressure(Exception error)
        {
            ZeroPressure=false;
            Last="保持零压力已停止："+error.GetBaseException().Message;
        }

        public void BeforeEnergyChange(ISlot slot,ref long amount,bool additive)
        {
            Observe(slot);
            if(!NoEnergyLoss)return;
            if(!additive && requestedSession==Session && requestedEnergy==amount){
                requestedEnergy=null;
                return;
            }
            long floor=0;
            if(!additive){
                long raw=slot.Base("Execution");
                if(amount>=raw)return;
                long bonus=checked(slot.Effective("Execution")-raw);
                floor=Math.Min(raw,Math.Max(0,checked(EnergyCap(slot)-bonus)));
            }
            if(amount>=floor)return;
            Protect(slot);
            amount=floor;
        }

        public void StopEnergy(Exception error)
        {
            NoEnergyLoss=false;
            Last="行动力不减少已停止："+error.GetBaseException().Message;
        }

        private static long Parse(string value)
        {
            long result;
            if(!Int64.TryParse(value,NumberStyles.AllowLeadingSign,CultureInfo.InvariantCulture,out result))
                throw new ArgumentException("请输入完整的十进制整数。");
            return result;
        }

        private static long EnergyCap(ISlot slot)
        {
            long cap = slot.Effective("XinDonLiShangXian");
            if(cap < 0 || cap > Int32.MaxValue) throw new InvalidOperationException("当前行动力上限无效。");
            return cap;
        }
        private void SetEffective(ISlot slot, string key, long target)
        {
            long current=slot.Effective(key);
            if(current==target) return;
            long raw=checked(slot.Base(key)+(target-current));
            if(raw<0) throw new InvalidOperationException("目标低于装备加成所允许的基础值。");
            Write(slot,key,raw);
            if(slot.Effective(key)!=target) throw new InvalidOperationException("游戏显示值与目标不符，已停止。");
        }
        private void Write(ISlot slot,string key,long value)
        {
            if(writing) throw new InvalidOperationException("上一项修改仍在执行。");
            if(slot.Base(key)==value) return;
            writing=true;
            try {
                Protect(slot);
                if(key=="Execution"){requestedSession=Session;requestedEnergy=value;}
                slot.Set(key,value);
                if(slot.Base(key)!=value) throw new InvalidOperationException("游戏读回不符，请检查当前值。");
            } finally {requestedEnergy=null;requestedSession=null;writing=false;}
        }

        private void Protect(ISlot slot)
        {
            if(protectedSlot)return;
            slot.Backup();
            protectedSlot=true;
        }

        public void Tick(ISlot slot)
        {
            Observe(slot);
            if(writing)return;
            if(ZeroPressure){
                try {Write(slot,"Pressure",0);}
                catch(Exception error){StopPressure(error);}
            }
        }
        public void Interact(ISlot slot,Entry person)
        {
            Observe(slot);
            if(!FullFavor || writing || person == null || person.Full <= 0) return;
            try {
                if(slot.Effective(person.Key)>=person.Full) return;
                SetEffective(slot,person.Key,person.Full);
                Last = person.Name+"好感已满（"+person.Full+"）";
            } catch(Exception e){FullFavor=false;Last="自动好感已停止："+e.Message;}
        }
    }
}
