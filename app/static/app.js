document.addEventListener('DOMContentLoaded', () => {
  if (window.lucide) lucide.createIcons();
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebarOverlay');
  document.getElementById('menuToggle')?.addEventListener('click', () => {
    sidebar?.classList.add('open'); overlay?.classList.add('visible');
  });
  overlay?.addEventListener('click', () => {
    sidebar?.classList.remove('open'); overlay?.classList.remove('visible');
  });
  document.querySelectorAll('[data-open-modal]').forEach(button => {
    button.addEventListener('click', () => {
      const modal = document.getElementById(button.dataset.openModal);
      if (modal) {modal.classList.add('visible'); modal.setAttribute('aria-hidden', 'false');
        modal.querySelector('input:not([type="hidden"]), select, button')?.focus();}
    });
  });
  const close = (modal) => {modal.classList.remove('visible');modal.setAttribute('aria-hidden','true');};
  document.querySelectorAll('[data-close-modal]').forEach(button => {
    button.addEventListener('click', () => {const modal=button.closest('.modal-backdrop');if(modal)close(modal);});
  });
  document.querySelectorAll('.modal-backdrop').forEach(modal => {
    modal.addEventListener('click', (event) => {if(event.target===modal)close(modal);});
  });
  document.addEventListener('keydown', (event) => {
    if (event.key==='Escape') document.querySelectorAll('.modal-backdrop.visible').forEach(close);
  });
  document.querySelectorAll('[data-confirm]').forEach(button => {
    button.addEventListener('click', event => {
      if(!window.confirm(button.dataset.confirm)) event.preventDefault();
    });
  });
  document.querySelectorAll('[data-toggle-password]').forEach(button => {
    button.addEventListener('click', () => {
      const field=document.getElementById(button.dataset.togglePassword);
      if(field)field.type=field.type==='password'?'text':'password';
    });
  });
});
