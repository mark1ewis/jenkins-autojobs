
from util import *
from jenkins_autojobs import git


jenkins = j = None
jobexists = None
repo = r = GitRepo()

cmd = partial(git.main, ('jenkins-makejobs-git'))

base_config_dict = None
base_config_yaml = '''
jenkins: %s
repo: %s

template: master-job-1
namesep: '-'
namefmt: '{shortref}'
overwrite: true
enable: 'sticky'
substitute :
  '@@JOB_NAME@@' : '{shortref}'

ignore:
  - 'refs/heads/feature/.*-nobuild'

refs:
  - 'refs/heads/feature/(.*)'
  - 'refs/heads/scratch/(.*)':
      'namefmt':  '{shortref}'
'''

def setup_module(module):
    # print('Starting Jenkins ...')
    # j.start_server()

    global jenkins, j, jobexists
    global base_config_dict

    print('Looking for a running Jenkins instance')
    jenkins = j = JenkinsControl('127.0.0.1:60888', '60887')
    jobexists = partial(jenkins.py.job_exists)

    base_config_dict = yaml.load(StringIO(base_config_yaml % (j.url, r.url)))

    print('Removing all jobs ...')
    for job in j.getjobs():
        j.py.delete_job(job)

    print('Creating test jobs ...')
    j.createjob('master-job-1', pjoin(here, 'etc/master-job-git-config.xml'))

    print('Creating temporary git repo: %s' % repo.dir)
    repo.init()

def teardown_module(module):
    teardown_module_(module, jenkins, repo)

def teardown_function(f):
    teardown_function_(f, jenkins)

def pytest_funcarg__cfg(request):
    return deepcopy(base_config_dict)


@pytest.mark.parametrize(('branch', 'namefmt', 'namesep', 'expected'),[
('feature/one/two', '{shortref}',      '.', 'feature.one.two'),
('feature/one/two', 'test-{shortref}', '-', 'test-feature-one-two'),
('feature/one/two', 'test.{ref}',      '-', 'test.refs-heads-feature-one-two'), ])
def test_namefmt_namesep_global(cfg, branch, namefmt, namesep, expected):
    test_namefmt_namesep_global.job = expected

    cfg['namefmt'] = namefmt
    cfg['namesep'] = namesep

    with r.branch(branch):
        cmd(cfg)
        assert jobexists(expected)

@pytest.mark.parametrize(('branch', 'namefmt', 'namesep', 'expected'),[
('scratch/one/two', '{shortref}', '.', 'scratch.one.two'),
('scratch/one/two', 'test.{ref}', '_', 'test.refs_heads_scratch_one_two'),
('scratch/one/two', 'test.{shortref}', '_', 'test.scratch_one_two'), ])
def test_namefmt_namesep_inherit(cfg, branch, namefmt, namesep, expected):
    test_namefmt_namesep_inherit.job = expected

    cfg['refs'] = [{'refs/heads/%s' % branch : {
        'namesep' : namesep,
        'namefmt' : namefmt, }}]

    with r.branch(branch):
        cmd(cfg)
        assert jobexists(expected)

@pytest.mark.parametrize(('branch', 'regex', 'namefmt', 'expected'),[
('scratch/one/two/three', 'refs/heads/scratch/(.*)/(.*)/', '{0}-wip-{1}', 'one-wip-two'),
('scratch/one/two/three', 'refs/heads/scratch/(.*)/.*/(.*)', '{1}.{0}', 'three.one'),
('wip/alpha/beta/gamma',  'refs/heads/wip/(.*)/.*/(.*)', 'test-{1}.{0}', 'test-gamma.alpha'), ])
def test_namefmt_groups_inherit(cfg, branch, regex, namefmt, expected):
    test_namefmt_groups_inherit.job = expected
    cfg['namefmt'] = '.'
    cfg['refs'] = [{ regex : {'namefmt' : namefmt, }}]

    with r.branch(branch):
        cmd(cfg)
        assert jobexists(expected)

@pytest.mark.parametrize(('branch', 'sub', 'ejob', 'expected'),[
('feature/one/two', {'@@JOB_NAME@@' : '{shortref}'}, 'feature-one-two', 'feature-one-two'),
('feature/two/three', {'@@JOB_NAME@@' : 'one-{ref}'},  'feature-two-three', 'one-refs-heads-feature-two-three'),
])
def test_substitute(cfg, branch, sub, ejob, expected):
    test_substitute.job = ejob
    cfg['substitute'] = sub

    with r.branch(branch):
        cmd(cfg)
        assert jobexists(ejob)
        assert j.py.get_job_info(ejob)['description'] == expected

@pytest.mark.parametrize(('branch', 'ignores'),[
('wip/one/two',  ['wip/.*']),
('feature/zetta-nobuild', ['.*-nobuild'])])
def test_ignore(cfg, branch, ignores):
    test_ignore.job = branch.replace('/', cfg['namesep'])

    cfg['ignore'] = ignores
    with r.branch(branch):
        cmd(cfg)
        assert not jobexists(test_ignore.job)

@pytest.mark.parametrize(('branch', 'name', 'local'),[
('feature/config-one', 'origin/refs/heads/feature/config-one', 'feature/config-one'),])
def test_configxml_global(cfg, branch, name, local):
    job = branch.replace('/', cfg['namesep'])
    test_configxml_global.job = job

    with r.branch(branch):
        cmd(cfg)
        assert jobexists(job)

        configxml = jenkins.job_etree(job)

        scm_el = configxml.xpath('scm[@class="hudson.plugins.git.GitSCM"]')[0]
        el = scm_el.xpath('//hudson.plugins.git.BranchSpec/name')[0]
        assert el.text == local
        assert scm_el.xpath('//localBranch')[0].text == local

def test_overwrite_global(cfg, capsys):
    cfg['overwrite'] = False
    cfg['namefmt'] = 'samename'

    with r.branch('feature/one'):
        cmd(cfg)
        assert jobexists('samename')

    with r.branch('feature/one'):
        cmd(cfg)
        assert jobexists('samename')

        # :todo: find better way
        out, err = capsys.readouterr()
        assert 'create job' not in out

def test_enable_true(cfg):
    j.py.disable_job('master-job-1')
    cfg['enable'] = True

    with r.branch('feature/enable-true'):
        cmd(cfg)
        assert jobexists('feature-enable-true')
        assert j.enabled('feature-enable-true')

def test_enable_false(cfg):
    j.py.enable_job('master-job-1')
    cfg['enable'] = False

    with r.branch('feature/enable-false'):
        cmd(cfg)
        assert jobexists('feature-enable-false')
        assert not j.enabled('feature-enable-false')

def test_enable_template(cfg):
    cfg['enable'] = 'template'

    j.py.enable_job('master-job-1')
    with r.branch('feature/enable-template-one'):
        cmd(cfg)
        assert jobexists('feature-enable-template-one')
        assert j.enabled('feature-enable-template-one')

    j.py.disable_job('master-job-1')
    with r.branch('feature/enable-template-two'):
        cmd(cfg)
        assert jobexists('feature-enable-template-two')
        assert not j.enabled('feature-enable-template-two')

def test_enable_sticky(cfg):
    cfg['enable'] = 'sticky'
    cfg['overwrite'] = True

    j.py.disable_job('master-job-1')
    with r.branch('feature/enable-sticky-one'):
        cmd(cfg)
        assert jobexists('feature-enable-sticky-one')
        assert not j.enabled('feature-enable-sticky-one')

    j.py.enable_job('feature-enable-sticky-one')
    with r.branch('feature/enable-sticky-one'):
        cmd(cfg)
        assert j.enabled('feature-enable-sticky-one')

def test_inheritance_order(cfg):
    test_namefmt_groups_inherit.job = 'one-feature-bravo-four'
    cfg['refs'] = [
        { 'refs/heads/feature/bravo/(.*)' : {'namefmt' : 'one-{shortref}'} },
        { 'refs/heads/feature/(.*)'       : {'namefmt' : 'two-{shortref}'} },
    ]

    with r.branch('feature/bravo/four'):
        cmd(cfg)
        assert jobexists('one-feature-bravo-four')

def test_missing_template(cfg):
    cfg['template'] = 'does-not-exist'
    with raises(SystemExit):
        cmd(cfg)
