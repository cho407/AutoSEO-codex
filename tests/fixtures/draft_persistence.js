// Opt-in test-only mock server. No real account endpoints or browser-local storage.
(async () => {
  if (new URLSearchParams(location.search).get('fixture_persist') !== '1') return;
  const title = document.querySelector('[aria-label="제목"]');
  const naver = document.querySelector('.se-main-container');
  const source = document.querySelector('#source-body');
  const tags = document.querySelector('#tags');
  const mode = document.querySelector('#mode-button');
  const read = () => ({title: title.value, body: naver ? naver.innerHTML : source.value,
    tags: tags.innerHTML, mode: mode?.textContent});
  const saved = await (await fetch('/autoseo-fixture-store')).json();
  if (saved) {
    title.value = saved.title;
    tags.innerHTML = saved.tags;
    if (naver) naver.innerHTML = saved.body;
    else {
      source.value = saved.body;
      source.hidden = false;
      document.querySelector('#basic-body').hidden = true;
      mode.textContent = saved.mode;
    }
  }
  const old = document.querySelector(naver ? '#save' : '#draft-save');
  const save = old.cloneNode(true);
  old.replaceWith(save);
  save.onclick = async () => {
    document.querySelector('#status').textContent = '저장 중';
    await fetch('/autoseo-fixture-store', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(read())});
    document.querySelector('#status').textContent = '임시저장 완료';
  };
  window.fixtureLoaded = true;
})();
