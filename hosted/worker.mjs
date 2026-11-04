import {handleApi} from './lib/hosted-api.mjs';
const PAGES={'/guide':'/guide.html','/account':'/account.html','/status':'/status.html'};
export default {
 async fetch(request,env){
  const url=new URL(request.url);
  if(url.pathname.startsWith('/api/'))return handleApi(request,env.DB,env.SITE_ORIGIN?{origin:env.SITE_ORIGIN}:{});
  const page=PAGES[url.pathname];
  if(page){url.pathname=page;return env.ASSETS.fetch(new Request(url,request));}
  return env.ASSETS.fetch(request);
 }
};
