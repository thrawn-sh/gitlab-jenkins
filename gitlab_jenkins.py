#!/usr/bin/env python
# -*- coding: utf-8 -*-

# pip install python-gitlab
# pip install python-jenkins

import argparse
import hashlib
from lxml import etree
from lxml import objectify

import gitlab
import jenkins

class JenkinsXmlConfig(object):

    def __init__(self, project, gitlab_url, jenkins_server, jenkins_seed=''):
        self._project = project
        self._gitlab_url = gitlab_url
        self._jenkins_server = jenkins_server
        self._jenkins_seed = jenkins_seed
    
    def __xml_user_remote_configs(self):
        element = objectify.Element('userRemoteConfigs')

        config = objectify.Element('hudson.plugins.git.UserRemoteConfig')
        config.url = self._project.http_url_to_repo
        config.credentialsId = 'gitlab-credentials'
        objectify.deannotate(config)
        element.append(config)

        objectify.deannotate(element)
        return element

    def __xml_branches(self):
        element = objectify.Element('branches')

        branch = objectify.Element('hudson.plugins.git.BranchSpec')
        branch.name = ('*/%s' % self._project.default_branch)
        objectify.deannotate(branch)
        element.append(branch)

        objectify.deannotate(element)
        return element

    def __xml_scm(self):
        element = objectify.Element('scm')
        element.set('class', 'hudson.plugins.git.GitSCM')

        plugin = self._jenkins_server.get_plugin_info('git')
        element.set('plugin', 'git@' + plugin['version'])

        element.append(self.__xml_branches())
        element.configVersion = 2
        element.doGenerateSubmoduleConfigurations = False
        element.append(self.__xml_user_remote_configs())

        objectify.deannotate(element)
        return element

    def __xml_definition(self):
        element = objectify.Element('definition')
        element.set('class', 'org.jenkinsci.plugins.workflow.cps.CpsScmFlowDefinition')

        plugin = self._jenkins_server.get_plugin_info('workflow-cps')
        element.set('plugin', 'workflow-cps@' + plugin['version'])

        element.lightweight = True
        element.append(self.__xml_scm())
        element.scriptPath = 'Jenkinsfile'

        objectify.deannotate(element)
        return element

    def __html_project_description(self):
        description = self._project.description
        description += '<hr>Tags: '
        first = True
        for tag in get_tags_for_project(self._project):
            if first:
                first = False
            else:
                description += ', '

            description += '<a href="%s/explore/projects?tag=%s">%s</a>' % (self._gitlab_url, tag, tag)

        description += '<hr>'
        description += '<a href="%s">%s</a>' % (self._project.web_url, self._project.web_url)
        return description

    def __xml_flow_definition(self):
        element = objectify.Element('flow-definition')

        plugin = self._jenkins_server.get_plugin_info('workflow-job')
        element.set('plugin', 'workflow-job@' + plugin['version'])

        element.authToken = create_jenkins_token(self._project, self._jenkins_seed)
        element.append(self.__xml_definition())
        element.description = self.__html_project_description()
        element.disabled = False
        element.keepDependencies = False

        objectify.deannotate(element)
        return element

    def xml_config(self):
        configuration = self.__xml_flow_definition()

        etree.cleanup_namespaces(configuration)
        xml = etree.tostring(configuration, pretty_print=True)
        return xml

def clear_project_badges(project):
    print ' - clearing project badges'
    badges = project.badges.list()
    for badge in badges:
        badge.delete()

def clear_project_hooks(project):
    print ' - clearing project hooks'
    hooks = project.hooks.list()
    for hook in hooks:
        hook.delete()

def create_jenkins_pipeline_badge_link(project, jenkins_url):
    # FIXME URL encode
    return '%s/job/%s/' % (jenkins_url, project.path)

def create_jenkins_pipeline_badge_image(project, jenkins_url):
    # FIXME URL encode
    return '%s/buildStatus/icon?job=%s' % (jenkins_url, project.path)

def create_jenkins_hook_url(project, jenkins_url, jenkins_seed=''):
    token = create_jenkins_token(project, jenkins_seed)
    # FIXME URL encode
    return '%s/job/%s/build?TOKEN=%s' % (jenkins_url, project.path, token)

def create_jenkins_token(project, jenkins_seed=''):
    token = hashlib.sha256(jenkins_seed)
    token.update(project.path_with_namespace)
    return token.hexdigest()

def does_support_jenkins(project):
    return does_any_file_exist(project, 'Jenkinsfile')

def does_any_file_exist(project, *paths):
    for path in paths:
        try:
            project.files.get(file_path=path, ref='master')
            return True
        except gitlab.exceptions.GitlabGetError:
            pass

    return False

def update_project_hooks(project, jenkins_url, jenkins_seed=''):
    print ' + setting webhook to jenkins'
    hooks = project.hooks.list()
    hooks_size = len(hooks)

    url = create_jenkins_hook_url(project, jenkins_url, jenkins_seed)
    if hooks_size > 0:
        hook = hooks[0]
        hook.confidential_issues_events = False
        hook.enable_ssl_verification = True
        hook.issues_events = False
        hook.job_events = False
        hook.merge_requests_events = True
        hook.note_events = False
        hook.pipeline_events = False
        hook.push_events = True
        hook.push_events_branch_filter = None
        hook.tag_push_events = False
        hook.url = url
        hook.wiki_events = False
        hook.save()
    else:
        project.hooks.create({'confidential_issues_events': False, 'enable_ssl_verification': True, 'issues_events': False, 'job_events': False, 'merge_requests_events': True, 'note_events': False, 'pipeline_events': False, 'push_events': True, 'push_events_branch_filter': None, 'tag_push_events': False, 'url': url, 'wiki_page_events': False})
        
def update_project_badges(project, jenkins_url):
    print ' + setting project badges'
    badges = project.badges.list()
    badges_size = len(badges)

    image_link = create_jenkins_pipeline_badge_image(project, jenkins_url)
    link_url = create_jenkins_pipeline_badge_link(project, jenkins_url)
    if badges_size > 0:
        badge = badges[0]
        badge.image_link = image_link
        badge.link_url = link_url
        badge.save()
    else:
        project.badges.create({'image_url':image_link, 'link_url':link_url})

def update_protected_branches(project):
    print ' + protecting master branch'
    protected_branches = project.protectedbranches.list()
    for protected_branche in protected_branches:
        protected_branche.delete()

    project.protectedbranches.create({'name':'master', 'merge_access_level':gitlab.DEVELOPER_ACCESS, 'push_access_level':gitlab.MAINTAINER_ACCESS})

def update_project_settings(project):
    print ' + updating settings'
    project.container_registry_enabled = False
    project.default_branch = 'master'
    project.issues_enabled = False
    project.jobs_enabled = False
    project.lfs_enabled = True
    project.merge_method = 'ff'
    project.merge_requests_enabled = True
    project.shared_runners_enabled = False
    project.snippets_enabled = False
    project.wiki_enabled = False

def configure_jenkins(project, gitlab_url, jenkins_server, jenkins_seed):
    print ' * configuiring Jenkins pipeline'
    config_xml = JenkinsXmlConfig(project, gitlab_url, jenkins_server, jenkins_seed).xml_config()
    if not jenkins_server.job_exists(project.name):
        jenkins_server.create_job(project.name, config_xml)
    else:
        jenkins_server.reconfig_job(project.name, config_xml)

def get_tags_for_project(project):
    tags = set()

    # add all languages to tags
    languages = project.languages()
    for language, percen in languages.items():
        if percen >= 5:
            tags.add(language)

    if project.license:
        tags.add(project.license['key'].upper())

    if does_any_file_exist(project, 'Jenkinsfile'):
        tags.add('CI/CD')

    if does_any_file_exist(project, 'pom.xml'):
        tags.add('Maven')

    if does_any_file_exist(project, 'build.xml'):
        tags.add('Ant')

    return sorted(tags)

def update_project_tags(project):
    print ' + setting project tags'
    project.tag_list = get_tags_for_project(project)

def main():
    parser = argparse.ArgumentParser(description='Allign gitlab project configurations.')
    parser.add_argument('--gitlab-url', help='URL for gitlab instance', required=True)
    parser.add_argument('--gitlab-admin-token', help='gitlab administrator token', required=True)
    parser.add_argument('--jenkins-url', help='URL for jenkins instance', required=True)
    parser.add_argument('--jenkins-admin-user', help='jenkins administrator account', required=True)
    parser.add_argument('--jenkins-admin-password', help='jenkins administrator password', required=True)
    parser.add_argument('--jenkins-seed', help='jenkins seed')

    args = parser.parse_args()
    print '================================================================================'
    print 'gitlab-url  : "%s"' % args.gitlab_url
    print 'jenkins-url : "%s"' % args.jenkins_url
    print '================================================================================'
    gitlab_server = gitlab.Gitlab(url=args.gitlab_url, private_token=args.gitlab_admin_token, ssl_verify=True)
    gitlab_server.auth()

    jenkins_server = jenkins.Jenkins(url=args.jenkins_url, username=args.jenkins_admin_user, password=args.jenkins_admin_password)

    projects = gitlab_server.projects.list(all=True, order_by='id', sort='asc')
    first = True
    for project in projects:
        # reload with full information
        project = gitlab_server.projects.get(id=project.id, license=True, statistics=True, with_custom_attributes=True)
        if first:
            first = False
        else:
            print '--------------------------------------------------------------------------------'

        print '[%4d] %s' % (project.id, project.web_url)
        update_project_settings(project)
        update_protected_branches(project)
        update_project_tags(project)

        if project.archived:
            clear_project_badges(project)
            clear_project_hooks(project)
            project.save()
            continue

        if does_support_jenkins(project):
            update_project_badges(project, args.jenkins_url)
            update_project_hooks(project, args.jenkins_url, args.jenkins_seed)
            configure_jenkins(project, args.gitlab_url, jenkins_server, args.jenkins_seed)

        project.save()
    print '================================================================================'

if __name__ == '__main__':
    main()
