# -*- coding: utf-8 -*-
#
# Copyright (C) 2008 Emmanuel Blot <emmanuel.blot@free.fr>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://projects.edgewall.com/trac/.
#

from revtree import IRevtreeEnhancer, RevtreeEnhancer
from revtree.svgview import SvgOperation, SvgGroup
from trac.core import *
from trac.util.text import to_unicode

from trac.versioncontrol import NoSuchNode

__all__ = ['MergeInfoEnhancerModule']


def get_merge_info(repos, path, rev):
    """Extract merge information as a list"""
    props = repos.get_node_properties(path, rev)
    mergeprop = props and props.get('svn:mergeinfo')
    return mergeprop and mergeprop.split('\n') or []


class MergeInfoEnhancer(RevtreeEnhancer):
    """Enhancer to show merge operation, based on svn:mergeinfo properties.
    """

    def __init__(self, env, req, repos, svgrevtree):
        """Creates the internal data from the repository"""
        self._repos = repos
        self._svgrevtree = svgrevtree
        self._widgets = [[] for l in IRevtreeEnhancer.ZLEVELS]
        self._merges = []
        self._groups = []
        
        for branch in repos.branches().values():
            # FIXME: revtree should not contain an empty branch
            svgbranch = branch and svgrevtree.svgbranch(branch=branch)
            # ignores branches that are not shown
            if not svgbranch:
                continue

            # retrieve the list of all revtree changesets in the branch,
            # oldest to youngest
            chgsets = [(chg.rev, chg) for chg in branch.changesets()]
            chgsets.sort()
            chgsets = [c for r, c in chgsets] 

            # if the first changeset of a branch is a copy of another
            # changeset (from another branch), extract the properties of the
            # source changeset
            srcmergeprops = []
            if chgsets and chgsets[0].clone:
                (srev, spath) = branch.source()
                try:
                    srcmergeprops = get_merge_info(repos, spath, srev)
                except NoSuchNode, e:
                    env.log.error(e)

            # find all the changeset that have been created by svnmerge
            mergeops = []
            for chgset in chgsets:
                try:
                    mergeprops = get_merge_info(repos, branch.name, chgset.rev)
                except NoSuchNode, e:
                    env.log.error(e)
                    continue

                # discard all the merge information already set in the source
                # branch
                filterprops = [m for m in mergeprops if m not in srcmergeprops]
                if filterprops:
                    mergeops.append((chgset.rev, mergeprops))

            srcbrs = {}
            prevmerge = None
            for m in mergeops:
                (rev, merges) = m
                if prevmerge != merges:
                    for source in merges:
                        (srcbr, srcrev) = source.split(':')
                        srcbranch = repos.branch(to_unicode(srcbr[1:]))
                        if not srcbranch:
                            continue
                        if not srcbrs.has_key(srcbr):
                            revs = [chg.rev for chg in srcbranch.changesets()]
                            revs.sort()
                            srcbrs[srcbr] = revs
                        for srcrange in srcrev.split(','):
                            if srcrange.endswith('*'):
                                srcrange = srcrange[0:-1]
                            srcs = srcrange.split('-')
                            s1 = int(srcs[0])
                            s2 = int(len(srcs) > 1 and srcs[1] or srcs[0])
                            srcrevs = filter(lambda x: s1 <= x <= s2, 
                                             srcbrs[srcbr])
                            #print "Result (%s,%s) %s" % (s1, s2, srcrevs)
                            if not srcrevs:
                                continue
                            fchg = repos.changeset(srcrevs[0])
                            lchg = repos.changeset(srcrevs[-1])
                            cchg = repos.changeset(rev)
                            self._groups.append((branch, fchg, lchg))
                            self._merges.append((lchg, cchg))
                        
                            # update the list of non-merged source changesets
                            srcbrs[srcbr] = filter(lambda x: x not in srcrevs, 
                                                   srcbrs[srcbr])
                    # track last useful merge info
                    prevmerge = merges
                
    def build(self):
        """Build the enhanced widgets"""
        svgrt = self._svgrevtree
        # create groups of changesets
        for (dstbranch, first, last) in self._groups:
            svgsrcbr = svgrt.svgbranch(branchname=first.branchname)
            svgdstbr = svgrt.svgbranch(branch=dstbranch)
            if not svgsrcbr:
                continue
            fsvg = svgsrcbr.svgchangeset(first)
            lsvg = svgsrcbr.svgchangeset(last)
            color = svgdstbr.fillcolor().lighten()
            group = SvgGroup(svgrt, fsvg, lsvg, color, 40)
            self._widgets[IRevtreeEnhancer.ZBACK].append(group)

        # create inter-branch operations
        for (srcchg, dstchg) in self._merges:
            svgsrcbr = svgrt.svgbranch(branchname=srcchg.branchname)
            svgdstbr = svgrt.svgbranch(branchname=dstchg.branchname)
            if not svgsrcbr or not svgdstbr:
                continue
            svgsrcchg = svgsrcbr.svgchangeset(srcchg)
            svgdstchg = svgdstbr.svgchangeset(dstchg)
            op = SvgOperation(svgrt, svgsrcchg, svgdstchg, 
                              svgdstbr.strokecolor())
            self._widgets[IRevtreeEnhancer.ZMID].append(op)

        # build widgets
        for wl in self._widgets:
            map(lambda w: w.build(), wl)

    def render(self, level):
        """Renders the widgets, from background plane to foreground plane"""
        if level < len(IRevtreeEnhancer.ZLEVELS):
            map(lambda w: w.render(), self._widgets[level])


class MergeInfoEnhancerModule(Component):
    """Enhancer to show merge operation, based on svn:mergeinfo properties.
    
       This enhancer requires a SVN >= 1.5 repository. Previous releases of
       SVN do not manage the required information. This enhancer cannnot be
       used with repositories managed with the svnmerge.py tool 
    """

    implements(IRevtreeEnhancer)

    def create(self, env, req, repos, svgrevtree):
        return MergeInfoEnhancer(env, req, repos, svgrevtree)
