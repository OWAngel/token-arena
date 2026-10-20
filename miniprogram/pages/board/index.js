const api=require('../../lib/api');
const logic=require('../../lib/board');
Page({
  data:{day:logic.yesterday(),days:1,periods:[1,7,30],models:['全部模型'],modelIndex:0,rows:[],totalText:'0',outputText:'0',people:0,modelCount:0,loading:false,error:'',expanded:'',browseOnly:false},
  onShow(){return this.refresh();},
  onPullDownRefresh(){this.refresh().finally(()=>wx.stopPullDownRefresh());},
  onShareAppMessage(){return {title:'Spark Arena · 自愿分享你的 Spark 用量',path:'/pages/board/index'};},
  refresh(){
    const app=getApp(),live=!!app.globalData.apiBase;
    this.setData({loading:true,error:'',day:logic.yesterday(),browseOnly:!app.globalData.enrollmentOpen});
    const load=live?api.request('/v1/board'):new Promise((resolve,reject)=>wx.request({url:app.globalData.publicBoardUrl,timeout:20000,success:r=>r.statusCode===200?resolve(r.data):reject(new Error('公开榜单暂时无法读取。')),fail:()=>reject(new Error('无法读取榜单，请检查网络及微信 request 合法域名配置。'))}));
    return load.then(data=>{
      if(!data||!Array.isArray(data.reports))throw new Error('榜单数据暂时不可用。');
      this.board=data;
      const models=['全部模型',...[...new Set(data.reports.flatMap(r=>r.models.map(m=>m.model)))].sort()];
      this.setData({models,modelIndex:0});this.render();
    }).catch(error=>this.setData({error:error.message})).finally(()=>this.setData({loading:false}));
  },
  render(){if(this.board)this.setData(logic.aggregate(this.board,this.data.day,this.data.days,this.data.models[this.data.modelIndex]=== '全部模型'?'':this.data.models[this.data.modelIndex]));},
  period(e){this.setData({days:Number(e.currentTarget.dataset.days)});this.render();},
  model(e){this.setData({modelIndex:Number(e.detail.value)});this.render();},
  detail(e){const id=e.currentTarget.dataset.id;this.setData({expanded:this.data.expanded===id?'':id});},
  me(){wx.navigateTo({url:'/pages/me/index'});}
});
