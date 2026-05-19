import { useConfirm } from 'primevue/useconfirm';

export function useConfirmAction() {
  const confirm = useConfirm();

  const confirmAction = (options = {}) => new Promise((resolve) => {
    let resolved = false;
    const finish = (result) => {
      if (resolved) return;
      resolved = true;
      resolve(result);
    };

    confirm.require({
      header: options.header || 'Подтверждение',
      message: options.message || 'Подтвердите действие.',
      icon: options.icon || 'pi pi-exclamation-triangle',
      rejectLabel: options.rejectLabel || 'Отмена',
      acceptLabel: options.acceptLabel || 'Подтвердить',
      rejectProps: {
        severity: 'secondary',
        outlined: true,
      },
      acceptProps: {
        severity: options.acceptSeverity || 'danger',
      },
      accept: () => finish(true),
      reject: () => finish(false),
      onHide: () => finish(false),
    });
  });

  return { confirmAction };
}

