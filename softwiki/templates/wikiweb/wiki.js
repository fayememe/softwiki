
(function(){
  var body=document.body, base=body.getAttribute('data-base')||'';
  var input=document.getElementById('wiki-search');
  var box=document.getElementById('search-results');
  var random=document.getElementById('random-link');
  var data=null, loading=false;
  function load(cb){
    if(data) return cb();
    if(loading) return;
    loading=true;
    fetch(base+'search-index.json').then(function(r){return r.json()}).then(function(d){data=d;loading=false;cb()}).catch(function(){loading=false});
  }
  function render(q){
    if(!data) return;
    var s=q.toLowerCase();
    var hits=data.filter(function(x){return x.t.toLowerCase().indexOf(s)>=0||x.s.toLowerCase().indexOf(s)>=0}).slice(0,8);
    if(!hits.length){box.hidden=true;box.innerHTML='';return}
    box.innerHTML=hits.map(function(x){
      return '<a href="'+base+x.u+'"><span>'+x.t+'</span><span class="sr-type">'+x.y+'</span><span class="sr-desc">'+x.s+'</span></a>';
    }).join('');
    box.hidden=false;
  }
  if(input){
    input.addEventListener('focus',function(){load(function(){if(input.value)render(input.value)})});
    input.addEventListener('input',function(){load(function(){render(input.value)})});
    input.addEventListener('keydown',function(e){
      if(e.key==='Escape'){box.hidden=true;input.blur()}
      if(e.key==='Enter'&&data){var first=box.querySelector('a');if(first)window.location.href=first.href}
    });
    document.addEventListener('click',function(e){if(!e.target.closest('.search-wrap'))box.hidden=true});
  }
  if(random){
    random.addEventListener('click',function(e){
      e.preventDefault();
      load(function(){
        if(!data||!data.length)return;
        var x=data[Math.floor(Math.random()*data.length)];
        window.location.href=base+x.u;
      });
    });
  }
})();
