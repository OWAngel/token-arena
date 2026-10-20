const api=require('../../lib/api');
Page({
  data:{configured:false,user:null,nickname:'',consent:false,busy:false,error:'',pairingCode:'',pairExpires:0},
  onLoad(){this.setData({configured:!!getApp().globalData.apiBase});},
  onShow(){if(this.data.configured&&wx.getStorageSync('sparkArenaSession'))this.refresh();},
  onHide(){this.setData({pairingCode:''});},
  async perform(action){if(this.data.busy)return;this.setData({busy:true,error:''});try{await action();}catch(e){this.setData({error:e.message,...(e.status===401?{user:null,pairingCode:''}:{})});}finally{this.setData({busy:false});}},
  refresh(){return this.perform(async()=>{const user=await api.request('/v1/me');this.setData({user,nickname:user.nickname,consent:user.consent_public});});},
  login(){return this.perform(async()=>{if(!this.data.configured)throw new Error('微信版报名尚未开放。');const user=await api.login();this.setData({user,nickname:user.nickname,consent:user.consent_public});});},
  nickname(e){this.setData({nickname:e.detail.value});},
  consent(e){this.setData({consent:e.detail.value.length>0});},
  privacy(){wx.navigateTo({url:'/pages/privacy/index'});},
  enroll(){return this.perform(async()=>{
    if(!this.data.consent)throw new Error('请阅读并同意公开说明后再自主报名。');
    if(!this.data.nickname.trim())throw new Error('请填写展示昵称。');
    if(wx.requirePrivacyAuthorize)await new Promise((resolve,reject)=>wx.requirePrivacyAuthorize({success:resolve,fail:()=>reject(new Error('需完成微信隐私授权后才能保存昵称。'))}));
    const user=await api.request('/v1/profile','PUT',{nickname:this.data.nickname.trim(),consent_public:true});this.setData({user});
  });},
  pair(){return this.perform(async()=>{const r=await api.request('/v1/pair','POST',{});this.setData({pairingCode:r.pairing_code,pairExpires:Date.now()+r.expires_in*1000});});},
  copyCode(){if(Date.now()>=this.data.pairExpires){this.setData({pairingCode:'',error:'绑定码已过期，请重新生成。'});return;}wx.setClipboardData({data:this.data.pairingCode});},
  copyCommand(){
    const base=getApp().globalData.apiBase.replace(/'/g,"'\\''");
    wx.setClipboardData({data:"python3 -m arena.wechat_client bind --api-base '"+base+"' --url 'http://替换成你的sparkDash地址:5555' --consent-public"});
  },
  async confirm(title,content){return new Promise(resolve=>wx.showModal({title,content,success:r=>resolve(r.confirm),fail:()=>resolve(false)}));},
  async revoke(){if(await this.confirm('撤销所有设备？','已绑定设备将停止上报，榜单历史仍保留。'))return this.perform(async()=>{const user=await api.request('/v1/devices','DELETE');this.setData({user,pairingCode:''});});},
  async leave(){if(await this.confirm('退出公开榜单？','退出后所有设备授权失效，你的记录将从微信榜单隐藏。已被他人保存的公开副本无法保证删除。'))return this.perform(async()=>{const user=await api.request('/v1/profile','DELETE');this.setData({user,consent:false,pairingCode:''});});},
  logout(){return this.perform(async()=>{await api.request('/v1/session','DELETE');wx.removeStorageSync('sparkArenaSession');this.setData({user:null,nickname:'',consent:false,pairingCode:''});});}
});
