import http from 'http';

interface TestResult {
  name: string;
  passed: boolean;
  error?: string;
  details?: any;
}

const results: TestResult[] = [];

function request(options: http.RequestOptions, body?: any): Promise<{ status: number; headers: http.IncomingHttpHeaders; data: any }> {
  return new Promise((resolve, reject) => {
    const req = http.request(options, (res) => {
      let chunks = '';
      res.on('data', (d) => (chunks += d));
      res.on('end', () => {
        let parsed = chunks;
        try {
          parsed = JSON.parse(chunks);
        } catch {}
        resolve({ status: res.statusCode || 0, headers: res.headers, data: parsed });
      });
    });
    req.on('error', reject);
    if (body) {
      req.write(typeof body === 'string' ? body : JSON.stringify(body));
    }
    req.end();
  });
}

async function run() {
  console.log('=====================================================');
  console.log('         RAPTAR API & ORCHESTRATOR TEST SUITE       ');
  console.log('=====================================================');

  // Test 1: GET /api/agent/state
  try {
    const res = await request({ port: 3000, path: '/api/agent/state', method: 'GET' });
    if (res.status === 200 && res.data.status && typeof res.data.progress === 'number') {
      results.push({ name: '1. GET /api/agent/state', passed: true, details: { status: res.data.status, mode: res.data.mode } });
      console.log('  [OK] 1. GET /api/agent/state');
    } else {
      throw new Error(`Unexpected payload: ${JSON.stringify(res.data)}`);
    }
  } catch (e: any) {
    results.push({ name: '1. GET /api/agent/state', passed: false, error: e.message });
    console.log('  [FAIL] 1. GET /api/agent/state: ' + e.message);
  }

  // Test 2: Mode Toggle (Approval Gate vs Full Auto)
  try {
    // Set to approval
    const resApprove = await request(
      { port: 3000, path: '/api/agent/mode', method: 'POST', headers: { 'Content-Type': 'application/json' } },
      { mode: 'approval' }
    );
    if (resApprove.status !== 200 || resApprove.data.mode !== 'approval') {
      throw new Error('Failed to set approval mode');
    }

    // Verify agent state reports approval
    const stateCheck = await request({ port: 3000, path: '/api/agent/state', method: 'GET' });
    if (stateCheck.data.mode !== 'approval') {
      throw new Error(`State did not reflect approval mode: ${stateCheck.data.mode}`);
    }

    // Test invalid mode rejects with 400
    const resInvalid = await request(
      { port: 3000, path: '/api/agent/mode', method: 'POST', headers: { 'Content-Type': 'application/json' } },
      { mode: 'invalid_mode' }
    );
    if (resInvalid.status !== 400) {
      throw new Error(`Expected 400 Bad Request, got ${resInvalid.status}`);
    }

    results.push({ name: '2. POST /api/agent/mode Toggle & Validation', passed: true });
    console.log('  [OK] 2. POST /api/agent/mode Toggle & Validation');
  } catch (e: any) {
    results.push({ name: '2. POST /api/agent/mode Toggle & Validation', passed: false, error: e.message });
    console.log('  [FAIL] 2. POST /api/agent/mode Toggle & Validation: ' + e.message);
  }

  // Test 3: Agent Pause / Resume controls
  try {
    const pauseRes = await request({ port: 3000, path: '/api/agent/pause', method: 'POST' });
    if (pauseRes.status !== 200 || !pauseRes.data.isPaused) throw new Error('Pause failed');

    const resumeRes = await request({ port: 3000, path: '/api/agent/resume', method: 'POST' });
    if (resumeRes.status !== 200 || resumeRes.data.isPaused) throw new Error('Resume failed');

    results.push({ name: '3. Agent Pause / Resume Controls', passed: true });
    console.log('  [OK] 3. Agent Pause / Resume Controls');
  } catch (e: any) {
    results.push({ name: '3. Agent Pause / Resume Controls', passed: false, error: e.message });
    console.log('  [FAIL] 3. Agent Pause / Resume Controls: ' + e.message);
  }

  // Test 4: GET /api/videos Catalog
  try {
    const res = await request({ port: 3000, path: '/api/videos', method: 'GET' });
    if (res.status === 200 && Array.isArray(res.data.videos)) {
      results.push({ name: '4. GET /api/videos Catalog', passed: true, details: { count: res.data.videos.length } });
      console.log(`  [OK] 4. GET /api/videos Catalog (${res.data.videos.length} videos found)`);
    } else {
      throw new Error('Invalid videos list');
    }
  } catch (e: any) {
    results.push({ name: '4. GET /api/videos Catalog', passed: false, error: e.message });
    console.log('  [FAIL] 4. GET /api/videos Catalog: ' + e.message);
  }

  // Test 5: GET /api/trends Radar
  try {
    const res = await request({ port: 3000, path: '/api/trends', method: 'GET' });
    if (res.status === 200 && Array.isArray(res.data.ideas) && res.data.ideas.length > 0) {
      results.push({ name: '5. GET /api/trends Radar Signals', passed: true, details: { ideas_count: res.data.ideas.length } });
      console.log(`  [OK] 5. GET /api/trends Radar Signals (${res.data.ideas.length} ideas available)`);
    } else {
      throw new Error('Failed to retrieve trend ideas');
    }
  } catch (e: any) {
    results.push({ name: '5. GET /api/trends Radar Signals', passed: false, error: e.message });
    console.log('  [FAIL] 5. GET /api/trends Radar Signals: ' + e.message);
  }

  // Test 6: GET & PUT /api/memory
  try {
    const memRes = await request({ port: 3000, path: '/api/memory', method: 'GET' });
    if (memRes.status !== 200 || !memRes.data.categoryWeights) throw new Error('Failed reading memory');

    // Mutate weight
    const updateRes = await request(
      { port: 3000, path: '/api/memory', method: 'PUT', headers: { 'Content-Type': 'application/json' } },
      { categoryWeights: { ...memRes.data.categoryWeights, 'space and astronomy': 1.85 } }
    );
    if (updateRes.status !== 200) throw new Error('Failed updating memory weights');

    results.push({ name: '6. GET & PUT /api/memory Calibration', passed: true });
    console.log('  [OK] 6. GET & PUT /api/memory Calibration');
  } catch (e: any) {
    results.push({ name: '6. GET & PUT /api/memory Calibration', passed: false, error: e.message });
    console.log('  [FAIL] 6. GET & PUT /api/memory Calibration: ' + e.message);
  }

  // Test 7: HTTP 206 Partial Content Media Streaming
  try {
    const streamRes = await request({
      port: 3000,
      path: '/api/media/output/video.mp4',
      method: 'GET',
      headers: { Range: 'bytes=0-1023' },
    });
    if (streamRes.status === 206 && streamRes.headers['content-range']) {
      results.push({ name: '7. HTTP 206 Partial Content Video Streaming', passed: true, details: { content_range: streamRes.headers['content-range'] } });
      console.log(`  [OK] 7. HTTP 206 Partial Content Video Streaming (${streamRes.headers['content-range']})`);
    } else {
      throw new Error(`Expected HTTP 206, got HTTP ${streamRes.status}`);
    }
  } catch (e: any) {
    results.push({ name: '7. HTTP 206 Partial Content Video Streaming', passed: false, error: e.message });
    console.log('  [FAIL] 7. HTTP 206 Partial Content Video Streaming: ' + e.message);
  }

  console.log('\n=====================================================');
  const passed = results.filter((r) => r.passed).length;
  const failed = results.filter((r) => !r.passed).length;
  console.log(`API Tests Total: ${results.length} | Passed: ${passed} | Failed: ${failed}`);
  if (failed > 0) process.exit(1);
}

run();
