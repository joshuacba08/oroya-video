import { DialogService } from './dialog.service';

describe('DialogService', () => {
  it('resolves a confirmation with the user choice', async () => {
    const dialogs = new DialogService();

    const accepted = dialogs.confirm({ title: 't', message: 'm', confirmLabel: 'ok' });
    dialogs.close(true);
    const cancelled = dialogs.confirm({ title: 't', message: 'm', confirmLabel: 'ok' });
    dialogs.close(null);

    expect(await accepted).toBe(true);
    expect(await cancelled).toBe(false);
    expect(dialogs.current()).toBeNull();
  });

  it('returns trimmed prompt text, or null when empty or cancelled', async () => {
    const dialogs = new DialogService();

    const named = dialogs.prompt({ title: 't', label: 'l', value: 'a', confirmLabel: 'ok' });
    dialogs.close('  Nuevo nombre  ');
    const empty = dialogs.prompt({ title: 't', label: 'l', value: 'a', confirmLabel: 'ok' });
    dialogs.close('   ');

    expect(await named).toBe('Nuevo nombre');
    expect(await empty).toBeNull();
  });

  it('cancels an open dialog when another one opens', async () => {
    const dialogs = new DialogService();

    const first = dialogs.confirm({ title: '1', message: 'm', confirmLabel: 'ok' });
    void dialogs.confirm({ title: '2', message: 'm', confirmLabel: 'ok' });

    expect(await first).toBe(false);
    expect(dialogs.current()?.title).toBe('2');
  });
});
