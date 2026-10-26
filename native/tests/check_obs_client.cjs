const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../src/youtube_music_native/assets/overlay/overlay.js'), 'utf8');
function element() {
  return {hidden:false,textContent:'',parentElement:{clientWidth:400},style:{setProperty(){}},classList:{values:[],add(x){this.values.push(x)},remove(){}},removeAttribute(name){delete this[name]}};
}
async function run(search, hash='', replies=[]) {
  const nodes = new Map(), calls = [], intervals = [];
  const context = vm.createContext({
    document:{body:element(),documentElement:element(),getElementById(name){if(!nodes.has(name))nodes.set(name,element());return nodes.get(name)}},
    location:{search,hash},URLSearchParams,URL,AbortController,AbortSignal,performance:{now:()=>0},
    setInterval(fn){intervals.push(fn)},setTimeout(){},clearTimeout(){},addEventListener(){},
    fetch:async(path, options)=>{calls.push({path, options});return replies.length?replies.shift():new Promise(()=>{})}
  });
  vm.runInContext(source,context);
  for(let i=0;i<8;i++)await new Promise(setImmediate);
  return {context,nodes,calls,intervals};
}
(async()=>{
  for(const layout of ['full','compact','text','badge','poster','ticker','display']) {
    const {context,nodes,calls}=await run('?preview=1&layout='+layout);
    assert(context.document.body.classList.values.includes(layout));
    assert.equal(nodes.get('title').textContent,'After the rain');
    assert.equal(nodes.get('preview').hidden,false);
    assert.equal(calls.length,0);
  }
  let result=await run('?layout=evil&art=0&progress=0');
  assert(result.context.document.body.classList.values.includes('full'));
  assert(result.nodes.get('artwork').hidden && result.nodes.get('progress').hidden);
  assert.equal(result.calls.length,0);
  const state={revision:12,playback:{state:'playing',duration:120,position:30},track:{title:'<img src=x onerror=alert(1)>',artists:['Fixture artist'],artwork:'https://private.invalid/signed'}};
  result=await run('', '#token=fixture-read-only', [{ok:true,json:async()=>state}]);
  assert.equal(result.nodes.get('title').textContent,state.track.title);
  assert.equal(result.nodes.get('fill').style.width,'25%');
  assert(result.calls.every(call=>call.path.startsWith('/v1/')&&!call.path.includes('token')));
  assert.equal(result.calls[0].options.headers.Authorization,'Bearer fixture-read-only');
  assert.equal(result.calls[0].options.credentials,'omit');
  assert.equal(result.calls[0].options.referrerPolicy,'no-referrer');
  assert.equal(result.calls[1].path,'/v1/events?after=12&timeout=20');
  result=await run('', '#token=fixture-read-only', [{ok:false,status:401}]);
  assert(result.nodes.get('card').hidden);
  assert(result.nodes.get('notice').textContent.includes('revoked'));
  assert.equal(result.calls.length,1);
  result=await run('?paused=hide','#token=fixture-read-only',[{ok:true,json:async()=>({...state,playback:{state:'paused'}})}]);
  assert(result.nodes.get('card').hidden);
  result=await run('','#token=fixture-read-only',[{ok:true,json:async()=>({revision:2,playback:{state:'stopped'},track:null})}]);
  assert.equal(result.nodes.get('notice').textContent,'Nothing playing');
  // A previous cover may finish after a track change; it must never replace the new one.
  let completeOld;
  const oldBlob = new Promise(resolve => { completeOld = resolve; });
  const firstArt = {...state,track:{...state.track,artwork:'/v1/artwork/'+'a'.repeat(24)}};
  const secondArt = {...firstArt,revision:13,track:{...firstArt.track,artwork:'/v1/artwork/'+'b'.repeat(24)}};
  result=await run('','#token=fixture-read-only',[
    {ok:true,json:async()=>firstArt}, {ok:true,blob:()=>oldBlob},
    {ok:true,json:async()=>secondArt}, {ok:true,blob:async()=>new Blob(['GIF89a'],{type:'image/gif'})}
  ]);
  const newestCover=result.nodes.get('cover').src;
  assert(newestCover.startsWith('blob:'));
  assert(result.calls[1].options.signal.aborted);
  completeOld(new Blob(['old'],{type:'image/png'}));
  for(let i=0;i<4;i++)await new Promise(setImmediate);
  assert.equal(result.nodes.get('cover').src,newestCover);
  URL.revokeObjectURL(newestCover);
  // A transient artwork error is retried on a later snapshot of the same track.
  result=await run('','#token=fixture-read-only',[
    {ok:true,json:async()=>firstArt}, {ok:false,status:503},
    {ok:true,json:async()=>({...firstArt,revision:13})}, {ok:true,blob:async()=>new Blob(['cover'],{type:'image/png'})}
  ]);
  assert.equal(result.calls.filter(call=>call.path===firstArt.track.artwork).length,2);
  URL.revokeObjectURL(result.nodes.get('cover').src);
  console.log('OBS layouts, fragment authentication, metadata escaping, revocation, stale covers and empty/paused states passed.');
})();
