import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { of, throwError } from 'rxjs';

import { NotificationService } from '../notifications/notification.service';
import { BatchService } from './batch.service';
import { ImportService, parseManualPaths } from './import.service';
import { OroyaDataService } from './oroya-data.service';

describe('ImportService', () => {
  const notifications = { danger: vi.fn() };
  const router = { navigate: vi.fn().mockResolvedValue(true) };

  function setup(failingPath?: string): { imports: ImportService; batch: BatchService } {
    notifications.danger.mockReset();
    router.navigate.mockClear();
    const data = {
      importPickedVideo: (selection: { path: string }) =>
        selection.path === failingPath
          ? throwError(() => new Error('broken'))
          : of({ id: `id-${selection.path}`, name: selection.path }),
      toErrorVm: (error: Error) => ({ message: error.message }),
    };
    TestBed.configureTestingModule({
      providers: [
        { provide: OroyaDataService, useValue: data },
        { provide: NotificationService, useValue: notifications },
        { provide: Router, useValue: router },
      ],
    });
    return { imports: TestBed.inject(ImportService), batch: TestBed.inject(BatchService) };
  }

  it('reads one path per line or separated by semicolons', () => {
    expect(parseManualPaths('C:\\a.mp4\n "C:\\b c.mp4" ; ;C:\\d.mov\n').map((p) => p.path)).toEqual([
      'C:\\a.mp4',
      'C:\\b c.mp4',
      'C:\\d.mov',
    ]);
  });

  it('opens the workspace for a single video', async () => {
    const { imports, batch } = setup();

    await imports.importAndContinue(parseManualPaths('a.mp4'));

    expect(router.navigate).toHaveBeenCalledWith(['/projects', 'id-a.mp4']);
    expect(batch.pending()).toBeNull();
  });

  it('keeps importing when one file fails and offers the rest as a batch', async () => {
    const { imports, batch } = setup('b.mp4');

    const result = await imports.importAndContinue(parseManualPaths('a.mp4\nb.mp4\nc.mp4'));

    expect(result.projects.map((project) => project.id)).toEqual(['id-a.mp4', 'id-c.mp4']);
    expect(result.failures.map((failure) => failure.path)).toEqual(['b.mp4']);
    expect(notifications.danger).toHaveBeenCalledOnce();
    expect(batch.pending()?.length).toBe(2);
    expect(imports.importing()).toBe(false);
  });
});
