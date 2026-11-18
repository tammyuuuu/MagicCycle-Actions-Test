const search = document.querySelector('#research-search');
const status = document.querySelector('#research-status');
const studies = [...document.querySelectorAll('.archive-grid .study')];
const feedback = document.querySelector('#search-feedback');

function filterStudies() {
  const query = search.value.trim().toLocaleLowerCase();
  let visible = 0;
  for (const study of studies) {
    const matchesText = study.dataset.search.toLocaleLowerCase().includes(query);
    const matchesStatus = status.value === '全部' || study.dataset.status === status.value;
    study.hidden = !(matchesText && matchesStatus);
    if (!study.hidden) visible += 1;
  }
  document.querySelector('#empty-results').hidden = visible > 0;
  feedback.textContent = query || status.value !== '全部' ? `显示 ${visible} 项研究` : '';
}
search.addEventListener('input', filterStudies);
status.addEventListener('change', filterStudies);
