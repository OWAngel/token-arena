function request(path, method, data) {
  const app = getApp();
  if (!app.globalData.apiBase) return Promise.reject(new Error('微信版报名尚未开放，可以先浏览公开榜单。'));
  return new Promise((resolve, reject) => {
    const token = wx.getStorageSync('sparkArenaSession');
    wx.request({
      url: app.globalData.apiBase + path, method: method || 'GET', data,
      header: { 'content-type': 'application/json', ...(token ? {Authorization:'Bearer '+token} : {}) },
      timeout: 20000,
      success(res) {
        if (res.statusCode === 200 && res.data && typeof res.data === 'object') return resolve(res.data);
        if (res.statusCode === 401) wx.removeStorageSync('sparkArenaSession');
        const error=new Error((res.data && res.data.error) || '请求未成功，请稍后重试。');error.status=res.statusCode;reject(error);
      },
      fail() { reject(new Error('网络暂时不可用，请检查网络后重试。')); }
    });
  });
}
function login() {
  return new Promise((resolve,reject)=>wx.login({success:r=>r.code?resolve(r.code):reject(new Error('微信登录未成功。')),fail:()=>reject(new Error('微信登录未成功。'))}))
    .then(code=>request('/v1/wechat/login','POST',{code}))
    .then(result=>{wx.setStorageSync('sparkArenaSession',result.access_token);return result.user;});
}
module.exports={request,login};
